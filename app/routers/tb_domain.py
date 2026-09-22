"""TB API domain mock — the target the v2 test screen calls.

The ext.apiops test screen (design 08 §8) calls the API that is deployed on TB, through the
TB domain — not through a particular gateway. The domain comes from the API group's test base
URL (KOA_TB_API_SPC.API_VERI_BASEURL) or, when that is empty, from `gateway.al.tbUrl`.
Locally `gateway.al.tbUrl` points here:

    gateway.al.tbUrl -> http://127.0.0.1:8090/tbdomain

so a call to  <domain> + /psso/v1.0/CAPRI_psso_defaultJoin  lands on
    /tbdomain/psso/v1.0/CAPRI_psso_defaultJoin

Any method and any path are accepted. The response follows the KT common response shape that
the existing code reads (CpApiResponse: transactionid / returnCode / returnDescription /
errorCode / errorDescription / response), and echoes what was received under "response.echo"
so the screen can be checked end to end.

Modes, switched through the control endpoint:
    ok       HTTP 200, returnCode "1"                        (default)
    fail     HTTP <status> (default 400), returnCode "0"     business / client error
    timeout  sleeps <delay_ms> (default 35000) before answering, to trip the caller's timeout

Control (mock only):
    GET /tbdomain/_ctl
    PUT /tbdomain/_ctl   {"mode": "ok|fail|timeout", "status": 400, "delay_ms": 35000, "body": {...}}
        `body` (optional) replaces the whole response body in "ok" / "fail" mode.
    DELETE /tbdomain/_ctl   back to defaults
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["tb-domain"])

_DEFAULTS: dict[str, Any] = {"mode": "ok", "status": 400, "delay_ms": 35000, "body": None}
_ctl: dict[str, Any] = dict(_DEFAULTS)


class CtlReq(BaseModel):
    mode: Literal["ok", "fail", "timeout"] | None = None
    status: int | None = None
    delay_ms: int | None = None
    body: dict[str, Any] | None = None


# --------------------------------------------------------------------- control
# Registered before the catch-all route so "_ctl" is not taken as an API path.

@router.get("/tbdomain/_ctl")
def get_ctl() -> dict[str, Any]:
    return _ctl


@router.put("/tbdomain/_ctl")
def put_ctl(req: CtlReq) -> dict[str, Any]:
    for key, value in req.model_dump(exclude_none=True).items():
        _ctl[key] = value
    return _ctl


@router.delete("/tbdomain/_ctl")
def reset_ctl() -> dict[str, Any]:
    _ctl.clear()
    _ctl.update(_DEFAULTS)
    return _ctl


# --------------------------------------------------------------------- API under test

@router.api_route("/tbdomain/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def call_api(path: str, request: Request) -> JSONResponse:
    raw = await request.body()
    try:
        received: Any = json.loads(raw) if raw else None
    except ValueError:
        received = raw.decode("utf-8", errors="replace")

    tx_id = received.get("transactionid") if isinstance(received, dict) else None
    echo = {
        "method": request.method,
        "path": "/" + path,
        "query": dict(request.query_params),
        "body": received,
    }

    mode = _ctl["mode"]
    if mode == "timeout":
        await asyncio.sleep(_ctl["delay_ms"] / 1000)

    if mode == "fail":
        body = _ctl["body"] or {
            "transactionid": tx_id or str(uuid.uuid4()),
            "returnCode": "0",
            "returnDescription": "Fail",
            "errorCode": f"E{_ctl['status']}",
            "errorDescription": "[mock] 실패 흉내",
            "response": {"echo": echo},
        }
        return JSONResponse(status_code=_ctl["status"], content=body)

    body = _ctl["body"] or {
        "transactionid": tx_id or str(uuid.uuid4()),
        "returnCode": "1",
        "returnDescription": "Success",
        "response": {"echo": echo},
    }
    return JSONResponse(status_code=200, content=body)
