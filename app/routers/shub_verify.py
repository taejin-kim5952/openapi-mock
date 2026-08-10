"""SHUB 2FA verify mock — POST /verify/v1.0/verify_send, /verify/v1.0/verify_check.

Mirrors what openapi-mng-dev (ShubRestApiCallFunction.shubAnyCommonApiCall via
LoginController's OTP flow) sends and expects. Unlike the PSSO endpoint, the
response body is NOT wrapped in a "response" key — the Java caller reads
`returncode` / `errordescription` directly off the top-level map.

Local-dev convenience: since there's no real SMS/email delivery locally,
both endpoints always succeed (returncode "1") regardless of phone/email/
auth_no — there's nothing for the user to receive and re-enter correctly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["shub-verify"])

SUCCESS_RETURN_CODE = "1"


class VerifySendReq(BaseModel):
    phone_number: str | None = None
    email: str | None = None
    verify: str | None = None


class VerifyCheckReq(BaseModel):
    phone_number: str | None = None
    email: str | None = None
    verify: str | None = None
    auth_no: str | None = None


class VerifyRes(BaseModel):
    returncode: str
    errordescription: str = ""


@router.post("/verify/v1.0/verify_send", response_model=VerifyRes)
async def verify_send(body: VerifySendReq) -> VerifyRes:
    _ = body  # accepted but not enforced (local mock, no real SMS/email dispatch)
    return VerifyRes(returncode=SUCCESS_RETURN_CODE)


@router.post("/verify/v1.0/verify_check", response_model=VerifyRes)
async def verify_check(body: VerifyCheckReq) -> VerifyRes:
    _ = body  # any auth_no is accepted locally
    return VerifyRes(returncode=SUCCESS_RETURN_CODE)
