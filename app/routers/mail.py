"""API Link mail send mock — POST /rest/procsendMail.

Mirrors what openapi-mng-dev's SendMailUtil.sendMailcall() sends
(templateId + inData{mailKey,title,contents,toMail}) and expects back
(a BaseResponse-shaped {code, message, total, results}).

Local-dev convenience: since there's no real mail relay locally, this
always succeeds regardless of payload content.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["mail"])

SUCCESS_CODE = "0000"


@router.post("/rest/procsendMail")
async def proc_send_mail(request: Request) -> dict[str, Any]:
    body = await request.json()
    _ = body  # accepted but not enforced (local mock, no real mail dispatch)
    return {
        "code": SUCCESS_CODE,
        "message": "success",
        "total": 0,
        "results": [],
    }
