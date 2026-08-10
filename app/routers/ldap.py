"""SHUB LDAP LoginProfile mock — POST /ldap/v3.1/loginprofile (OIF_24006)."""

from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.config import get_settings
from app.crypto.aes_gcm import decrypt, encrypt

router = APIRouter(tags=["ldap"])

SUCCESS_RETURN_CODE = "1"
FAIL_RETURN_CODE = "0"


class LdapLoginProfileReqBody(BaseModel):
    connID: str | None = None
    connPwd: str | None = None
    loginID: str | None = None
    loginPwd: str | None = None


class LdapLoginProfileReq(BaseModel):
    request: LdapLoginProfileReqBody | None = None


class LdapReturnResult(BaseModel):
    sn: str | None = None
    epmail: str | None = None
    epmobile: str | None = None
    epdeptn: str | None = None
    positionc: str | None = None
    positionn: str | None = None
    epcomc: str | None = None
    ssoUsOrgId: str | None = None
    pwdChangedDate: str | None = None
    pwdExpiredDate: str | None = None


class LdapLoginProfileResBody(BaseModel):
    returnresult: LdapReturnResult | None = None


class LdapLoginProfileRes(BaseModel):
    response: LdapLoginProfileResBody | None = None
    returncode: str | None = None
    returndescription: str | None = None
    transactionid: str | None = None
    sequenceno: str | None = None
    errorcode: str | None = None
    errordescription: str | None = None


def _encrypt_fields(values: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: encrypt(v, key) if isinstance(v, str) else v for k, v in values.items()}


@lru_cache
def _load_users(path_str: str) -> list[dict[str, Any]]:
    path = Path(path_str)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("users") or [])


def _find_user(login_id: str, login_pwd: str) -> dict[str, Any] | None:
    settings = get_settings()
    for user in _load_users(str(settings.ldap_users_file.resolve())):
        if user.get("login_id") == login_id and user.get("login_pwd") == login_pwd:
            return user
    return None


def _fail_response(message: str) -> LdapLoginProfileRes:
    return LdapLoginProfileRes(
        response=None,
        returncode=FAIL_RETURN_CODE,
        returndescription=message,
        transactionid=str(uuid.uuid4()),
        sequenceno="1",
        errorcode="LDAP_AUTH_FAIL",
        errordescription=message,
    )


@router.post("/ldap/v3.1/loginprofile", response_model=LdapLoginProfileRes)
async def login_profile(
    body: LdapLoginProfileReq,
    authorization: str | None = Header(default=None),
    mode: str | None = Header(default=None),
) -> LdapLoginProfileRes:
    """Accept encrypted LoginProfile request; return encrypted success profile or failure."""
    _ = authorization, mode  # accepted but not strictly validated (local mock)
    settings = get_settings()
    key = settings.ldap_aes_key
    req = body.request or LdapLoginProfileReqBody()

    login_id = decrypt(req.loginID, key) or ""
    login_pwd = decrypt(req.loginPwd, key) or ""
    # conn credentials are decrypted for parity; mock does not enforce them
    _ = decrypt(req.connID, key), decrypt(req.connPwd, key)

    if not login_id or not login_pwd:
        return _fail_response("loginID or loginPwd is empty or decrypt failed")

    user = _find_user(login_id, login_pwd)
    if user is None:
        return _fail_response("LDAP 아이디 또는 비밀번호를 확인해 주세요.")

    profile = dict(user.get("profile") or {})
    encrypted_profile = _encrypt_fields(profile, key)

    return LdapLoginProfileRes(
        response=LdapLoginProfileResBody(
            returnresult=LdapReturnResult(**encrypted_profile),
        ),
        returncode=SUCCESS_RETURN_CODE,
        returndescription="SUCCESS",
        transactionid=str(uuid.uuid4()),
        sequenceno="1",
        errorcode=None,
        errordescription=None,
    )


@router.get("/ldap/v3.1/loginprofile/users")
async def list_fixture_users() -> dict[str, Any]:
    """Dev helper: list mock login IDs (passwords omitted)."""
    settings = get_settings()
    users = _load_users(str(settings.ldap_users_file.resolve()))
    return {
        "users": [
            {"login_id": u.get("login_id"), "profile_sn": (u.get("profile") or {}).get("sn")}
            for u in users
        ]
    }
