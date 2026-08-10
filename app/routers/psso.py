"""PSSO memberLogin mock — POST /psso/v2.0/psso_memberLogin.

Mirrors what openapi-mng-dev (ShubRestApiCallFunction.funcForPsso /
LoginController) sends and expects:

Request  (already wrapped in `{"request": {...}}` by the Java caller):
    {"request": {"ClientKey": "...", "EncPSSOID": "<aes>", "EncPSSOPW": "<aes>"}}

Response (Java reads `response.*` directly, unwrapped from the HTTP body's
top-level "response" key):
    {"response": {"ReturnCode": "11", "ReturnName": "<aes>",
                  "ReturnMobile": "<aes>", "ReturnOtherm": "<aes>"}}

ReturnCode: "11" success; "12"-"16" various login failures (LoginController
maps all of them to the same "아이디/패스워드를 확인해주세요." message).

Local-dev convenience: any ID/PW that decrypts to a non-empty string succeeds.
Fixture users (app/fixtures/psso_users.yaml) get their configured name/mobile/
email; anything else gets a generic profile derived from the login id.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Header
from pydantic import BaseModel

from app.config import get_settings
from app.crypto.aes_cbc import decrypt, encrypt

router = APIRouter(tags=["psso"])

SUCCESS_RETURN_CODE = "11"
FAIL_RETURN_CODE = "12"


class PssoMemberLoginReqBody(BaseModel):
    ClientKey: str | None = None
    EncPSSOID: str | None = None
    EncPSSOPW: str | None = None


class PssoMemberLoginReq(BaseModel):
    request: PssoMemberLoginReqBody | None = None


class PssoMemberLoginResBody(BaseModel):
    ReturnCode: str
    ReturnName: str | None = None
    ReturnMobile: str | None = None
    ReturnOtherm: str | None = None


class PssoMemberLoginRes(BaseModel):
    response: PssoMemberLoginResBody


@lru_cache
def _load_users(path_str: str) -> list[dict[str, Any]]:
    path = Path(path_str)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("users") or [])


def _find_user(login_id: str, login_pwd: str) -> dict[str, Any] | None:
    settings = get_settings()
    for user in _load_users(str(settings.psso_users_file.resolve())):
        if user.get("login_id") == login_id and user.get("login_pwd") == login_pwd:
            return user
    return None


@router.post("/psso/v2.0/psso_memberLogin", response_model=PssoMemberLoginRes)
async def psso_member_login(
    body: PssoMemberLoginReq,
    authorization: str | None = Header(default=None),
) -> PssoMemberLoginRes:
    """Decrypt EncPSSOID/EncPSSOPW; return an AES-encrypted mock profile or a failure code."""
    _ = authorization  # accepted but not enforced (local mock)
    settings = get_settings()
    key = settings.psso_aes_key
    req = body.request or PssoMemberLoginReqBody()

    login_id = decrypt(req.EncPSSOID, key) or ""
    login_pwd = decrypt(req.EncPSSOPW, key) or ""

    if not login_id or not login_pwd:
        # decrypt itself failed (empty EncPSSOID/EncPSSOPW or wrong AES key) — a real
        # misconfiguration, not something the "always succeed" convenience should hide.
        return PssoMemberLoginRes(response=PssoMemberLoginResBody(ReturnCode=FAIL_RETURN_CODE))

    user = _find_user(login_id, login_pwd)
    if user is not None:
        profile = user.get("profile") or {}
    else:
        # not a configured fixture — still succeed locally, using the login id itself
        profile = {
            "name": login_id,
            "mobile": "01000000000",
            "email": f"{login_id}@mock.local",
        }

    return PssoMemberLoginRes(
        response=PssoMemberLoginResBody(
            ReturnCode=SUCCESS_RETURN_CODE,
            ReturnName=encrypt(profile.get("name", ""), key),
            ReturnMobile=encrypt(profile.get("mobile", ""), key),
            ReturnOtherm=encrypt(profile.get("email", ""), key),
        )
    )


@router.get("/psso/v2.0/psso_memberLogin/users")
async def list_fixture_users() -> dict[str, Any]:
    """Dev helper: list mock login IDs (passwords omitted)."""
    settings = get_settings()
    users = _load_users(str(settings.psso_users_file.resolve()))
    return {
        "users": [
            {"login_id": u.get("login_id"), "name": (u.get("profile") or {}).get("name")}
            for u in users
        ]
    }
