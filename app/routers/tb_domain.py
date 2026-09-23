"""TB API domain mock — the target the v2 test screen calls.

The ext.apiops test screen (design 08 §8) calls the API that is deployed on TB, through the
TB domain — not through a particular gateway. The domain comes from the API group's test base
URL (KOA_TB_API_SPC.API_VERI_BASEURL) or, when that is empty, from `gateway.al.tbUrl`.
Locally `gateway.al.tbUrl` points here:

    gateway.al.tbUrl -> http://127.0.0.1:8090/tbdomain

so a call to  <domain> + /psso/v1.0/CAPRI_psso_defaultJoin  lands on
    /tbdomain/psso/v1.0/CAPRI_psso_defaultJoin

Only APIs that were deployed on a TB gateway answer (`require_deploy`, on by default). The call
is matched against the deploy payloads stored by the BEAST mock — inbound path (`in`) and method
(`meth`) — so the screens follow the same order a real gateway enforces: deploy first, then call.
An undeployed path gets a 404 that says so. Turn the check off to accept any path, as before:

    PUT /tbdomain/_ctl  {"require_deploy": false}

The response follows the KT common response shape that
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

from app import store
from app.routers.beast import find_deployed

router = APIRouter(tags=["tb-domain"])

_DEFAULTS: dict[str, Any] = {
    "mode": "ok",
    "status": 400,
    "delay_ms": 35000,
    "body": None,
    # Only APIs deployed on a TB gateway answer. A real gateway routes what was deployed to it,
    # so a call to an undeployed path is a 404 there too — and that is the order the screens
    # teach (TB deploy, then test). Set false to answer any path, as before.
    "require_deploy": True,
}
_CTL_KEY = "tbdomain_ctl"
_ctl: dict[str, Any] = {**_DEFAULTS, **store.load(_CTL_KEY, {})}


def _save_ctl() -> None:
    store.save(_CTL_KEY, _ctl)


class CtlReq(BaseModel):
    mode: Literal["ok", "fail", "timeout"] | None = None
    status: int | None = None
    delay_ms: int | None = None
    body: dict[str, Any] | None = None
    require_deploy: bool | None = None


# --------------------------------------------------------------------- control
# Registered before the catch-all route so "_ctl" is not taken as an API path.

@router.get("/tbdomain/_ctl")
def get_ctl() -> dict[str, Any]:
    return _ctl


@router.put("/tbdomain/_ctl")
def put_ctl(req: CtlReq) -> dict[str, Any]:
    for key, value in req.model_dump(exclude_none=True).items():
        _ctl[key] = value
    _save_ctl()
    return _ctl


@router.delete("/tbdomain/_ctl")
def reset_ctl() -> dict[str, Any]:
    _ctl.clear()
    _ctl.update(_DEFAULTS)
    _save_ctl()
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

    # 배포된 API 만 답한다. 어느 게이트웨이의 어느 apiId 로 걸렸는지 응답에 함께 실어
    # "내가 방금 배포한 그것이 맞다" 를 화면에서 확인할 수 있게 한다.
    if _ctl["require_deploy"]:
        hit = find_deployed("/" + path, request.method)
        if hit is None:
            return JSONResponse(status_code=404, content={
                "transactionid": tx_id or str(uuid.uuid4()),
                "returnCode": "0",
                "returnDescription": "Not deployed",
                "errorCode": "E404",
                "errorDescription": (
                    f"[mock] 배포되지 않은 API 입니다 - {request.method} /{path}. "
                    "TB 배포를 먼저 하세요. (GET /beast/_ctl 로 올라간 목록을 볼 수 있습니다)"
                ),
                "response": {"echo": echo},
            })
        gw, api_id, _spec = hit
        echo["deployedOn"] = {"gateway": gw, "apiId": api_id}

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
