"""Microsoft Entra ID (OIDC) 흉내 — openapi-mng-dev-jdk21-new 로그인용.

실제 Entra ID 와 같은 절차(인가 코드 방식)를 그대로 밟는다. API Manager 쪽 코드는 운영용 그대로이고
설정의 주소만 이 서버로 돌린다. 외부망에서는 진짜 Entra ID 에 닿지 않기 때문이다.

    GET  /entra/{tenant}/oauth2/v2.0/authorize   로그인 화면 자리. 묻지 않고 바로 성공시켜 돌려보낸다
    POST /entra/{tenant}/oauth2/v2.0/token       인가 코드 -> access_token + id_token(RS256 서명)
    GET  /entra/{tenant}/discovery/v2.0/keys     id_token 서명 검증용 공개키(JWKS)
    GET  /entra/oidc/userinfo                    UserInfo (name · family_name · email)
    GET  /entra/{tenant}/v2.0/.well-known/openid-configuration

**무조건 성공한다.** 누구로 로그인할지는 authorize 의 `login_hint` 로 정한다(아이디만. 비밀번호 없음).
`login_hint` 가 없으면 아이디를 묻는 작은 화면을 보여 준다.

돌려주는 값의 모양은 2026-10-02 에 실제 Entra ID 에서 받은 응답을 따랐다(값은 전부 지어낸 것이다).
    id_token claim : aud iss iat nbf exp aio email name nonce oid preferred_username rh sid sub tid uti ver
    userinfo       : sub name family_name picture email
    email 의 @ 앞이 사번이고, API Manager 는 그것을 아이디로 쓴다.

서명 키는 서버가 뜰 때 새로 만든다(파일에 남기지 않는다). 목 서버를 다시 띄우면 kid 가 바뀌고,
받는 쪽은 JWKS 를 다시 읽어 간다.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import APIRouter, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter(tags=["entra"])

EMAIL_DOMAIN = "ktpartners.com"
UPN_DOMAIN = "ktcorp365.onmicrosoft.com"
CODE_TTL = 300          # 인가 코드 수명(초)
TOKEN_TTL = 3900        # 토큰 수명(초). 실제 응답이 65분이었다

# ---------------------------------------------------------------- 서명 키 (뜰 때 한 번)
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = secrets.token_urlsafe(20)

# 인가 코드 · 접근 토큰 -> 누구의 것인지. 메모리에만 둔다(재기동하면 사라진다)
_CODES: dict[str, dict[str, Any]] = {}
_TOKENS: dict[str, dict[str, Any]] = {}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _int_b64(n: int) -> str:
    return _b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def _sign(claims: dict[str, Any]) -> str:
    header = {"typ": "JWT", "alg": "RS256", "kid": _KID}
    head = _b64(json.dumps(header, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = _KEY.sign(f"{head}.{body}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{_b64(sig)}"


def _base(request: Request) -> str:
    """이 서버를 부른 주소. 발급자(iss)와 각 주소를 여기에 맞춘다 - 받는 쪽 설정의 발급자와 같아야 검증을 통과한다."""
    return str(request.base_url).rstrip("/")


def _issuer(request: Request, tenant: str) -> str:
    return f"{_base(request)}/entra/{tenant}/v2.0"


def _person(login_hint: str) -> dict[str, str]:
    """아이디 하나로 한 사람을 지어낸다. 같은 아이디는 언제나 같은 사람이다."""
    hint = login_hint.strip()
    user_id = hint.split("@", 1)[0]
    digest = hashlib.sha256(user_id.encode("utf-8")).digest()
    family = f"목사용자{user_id[-4:]}"
    return {
        "id": user_id,
        "email": hint if "@" in hint else f"{user_id}@{EMAIL_DOMAIN}",
        "upn": f"{user_id}@{UPN_DOMAIN}",
        "family_name": family,
        "name": f"{family}(kt ds협력사)",
        "sub": _b64(digest)[:43],
        "oid": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"entra-mock.{user_id}")),
    }


def _clean() -> None:
    now = time.time()
    for store in (_CODES, _TOKENS):
        for key in [k for k, v in store.items() if v["exp"] < now]:
            store.pop(key, None)


# ---------------------------------------------------------------- 설정 문서
@router.get("/entra/{tenant}/v2.0/.well-known/openid-configuration")
def openid_configuration(tenant: str, request: Request) -> dict[str, Any]:
    base = f"{_base(request)}/entra"
    return {
        "issuer": _issuer(request, tenant),
        "authorization_endpoint": f"{base}/{tenant}/oauth2/v2.0/authorize",
        "token_endpoint": f"{base}/{tenant}/oauth2/v2.0/token",
        "jwks_uri": f"{base}/{tenant}/discovery/v2.0/keys",
        "userinfo_endpoint": f"{base}/oidc/userinfo",
        "response_types_supported": ["code"],
        "subject_types_supported": ["pairwise"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "claims_supported": ["sub", "iss", "aud", "exp", "iat", "nonce", "name", "email", "preferred_username", "oid", "tid"],
    }


@router.get("/entra/{tenant}/discovery/v2.0/keys")
def jwks(tenant: str) -> dict[str, Any]:
    _ = tenant
    pub = _KEY.public_key().public_numbers()
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": _KID, "n": _int_b64(pub.n), "e": _int_b64(pub.e)}]}


# ---------------------------------------------------------------- 로그인 화면 자리
@router.get("/entra/{tenant}/oauth2/v2.0/authorize")
def authorize(
    tenant: str,
    request: Request,
    client_id: str = "",
    redirect_uri: str = "",
    response_type: str = "code",
    state: str = "",
    nonce: str = "",
    scope: str = "openid",
    login_hint: str = "",
):
    if response_type != "code" or not client_id or not redirect_uri.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="[mock] client_id · redirect_uri · response_type=code 가 필요합니다")

    if not login_hint.strip():
        # 누구로 들어갈지 정해지지 않았다. 아이디만 묻는다(비밀번호는 없다 - 무조건 성공하는 목이다)
        hidden = "".join(
            f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
            for k, v in request.query_params.items()
            if k != "login_hint"
        )
        return HTMLResponse(
            "<!doctype html><html lang='ko'><meta charset='utf-8'><title>Entra ID (mock)</title>"
            "<body style='font-family:sans-serif;max-width:420px;margin:80px auto'>"
            "<h2>Microsoft Entra ID <small>(mock)</small></h2>"
            "<p>로그인할 아이디(사번)를 입력하세요. 비밀번호는 묻지 않습니다.</p>"
            f"<form method='get'>{hidden}"
            "<input name='login_hint' autofocus required maxlength='50' style='padding:8px;width:240px'> "
            "<button style='padding:8px 16px'>로그인</button></form></body></html>"
        )

    _clean()
    code = secrets.token_urlsafe(32)
    _CODES[code] = {
        "tenant": tenant,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "nonce": nonce,
        "scope": scope,
        "person": _person(login_hint),
        "exp": time.time() + CODE_TTL,
    }
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode({'code': code, 'state': state})}", status_code=302)


# ---------------------------------------------------------------- 토큰
@router.post("/entra/{tenant}/oauth2/v2.0/token")
def token(
    tenant: str,
    request: Request,
    grant_type: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    client_id: str = Form(""),
    authorization: str | None = Header(default=None),
):
    # 클라이언트 인증은 값이 왔는지만 본다(목). client_secret_basic 이면 아이디가 헤더에 실려 온다
    if not client_id and authorization and authorization.lower().startswith("basic "):
        try:
            client_id = base64.b64decode(authorization[6:]).decode("utf-8").split(":", 1)[0]
        except Exception:  # noqa: BLE001 - 형식이 틀리면 아래에서 거절된다
            client_id = ""

    issued = _CODES.pop(code, None)      # 인가 코드는 한 번만 쓴다
    if grant_type != "authorization_code" or issued is None or issued["exp"] < time.time():
        return JSONResponse({"error": "invalid_grant", "error_description": "[mock] 인가 코드가 없거나 만료됐습니다"}, status_code=400)
    if issued["tenant"] != tenant or issued["redirect_uri"] != redirect_uri or (client_id and issued["client_id"] != client_id):
        return JSONResponse({"error": "invalid_grant", "error_description": "[mock] 인가 요청과 값이 다릅니다"}, status_code=400)

    person = issued["person"]
    now = int(time.time())
    claims = {
        "aud": issued["client_id"],
        "iss": _issuer(request, tenant),
        "iat": now,
        "nbf": now,
        "exp": now + TOKEN_TTL,
        "aio": _b64(secrets.token_bytes(48)),
        "email": person["email"],
        "name": person["name"],
        "nonce": issued["nonce"],
        "oid": person["oid"],
        "preferred_username": person["upn"],
        "rh": "1.mock." + secrets.token_urlsafe(24),
        "sid": str(uuid.uuid4()),
        "sub": person["sub"],
        "tid": tenant,
        "uti": secrets.token_urlsafe(16),
        "ver": "2.0",
    }
    if not issued["nonce"]:
        claims.pop("nonce")

    access_token = secrets.token_urlsafe(48)
    _TOKENS[access_token] = {"person": person, "exp": time.time() + TOKEN_TTL}
    return {
        "token_type": "Bearer",
        "scope": "User.Read openid profile email",
        "expires_in": TOKEN_TTL,
        "ext_expires_in": TOKEN_TTL,
        "access_token": access_token,
        "id_token": _sign(claims),
    }


# ---------------------------------------------------------------- UserInfo
@router.get("/entra/oidc/userinfo")
def userinfo(authorization: str | None = Header(default=None)):
    value = (authorization or "")
    token_value = value[7:] if value.lower().startswith("bearer ") else ""
    held = _TOKENS.get(token_value)
    if held is None or held["exp"] < time.time():
        return JSONResponse({"error": "invalid_token"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    person = held["person"]
    return {
        "sub": person["sub"],
        "name": person["name"],
        "family_name": person["family_name"],
        "picture": "https://graph.microsoft.com/v1.0/me/photo/$value",
        "email": person["email"],
    }
