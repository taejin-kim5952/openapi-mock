"""BEAST API gateway mock — deploy / query an API spec, per gateway.

Mirrors what openapi-mng-dev-jdk21-new sends through
`web.beast.service.BeastServiceImpl.procBeastApiRequest` and what it expects back.
The Java side builds the URL as  <gateway domain> + /apilink/v1/api/<op> + <query string>,
and picks the domain from config by target:

    TB_KTC    -> bstgw.api.tb.url       -> http://127.0.0.1:8090/beast/ktc
    TB_AZURE  -> bstgw.api.new.tb.url   -> http://127.0.0.1:8090/beast/azure
    PRD_KTC   -> bstgw.api.prd.url      -> http://127.0.0.1:8090/beast/prd-ktc
    PRD_AZURE -> bstgw.api.new.prd.url  -> http://127.0.0.1:8090/beast/prd-azure

Deploy   POST /beast/{gw}/apilink/v1/api/apiDply
    body : the BEAST deploy spec JSON (BstgwApiDplyEntity). `apiId` is the key.
    ok   : HTTP 200 {"common": {"code": 200, "message": "정상처리되었습니다."}}
    Java (bstgwApiDeploy) treats HTTP 200 + common.code == 200 as success.

Query    GET  /beast/{gw}/apilink/v1/api/getApiDplyById?apiId=...
    found     : HTTP 200 {"common": {...200}, "data": {"value": <stored spec>}}
    not found : HTTP 200 {"common": {...200}, "data": {}}      -> "없음(신규 배포)"
    ext.apiops judges this call by HTTP 200 only (design 08 §5 ③).

Two kinds of failure, switched per gateway through the control endpoints below:
    deploy = "fail"   -> HTTP 200 + common.code 400   (BEAST refused  -> Java NK)
    deploy = "error"  -> HTTP 500                      (transport fail -> Java ERR)
    query  = "error"  -> HTTP 500                      (-> ext.apiops stops the deploy)

Control (mock only — not part of BEAST):
    GET    /beast/_ctl                 switches + stored apiIds of every gateway
    PUT    /beast/_ctl/{gw}            {"deploy": "ok|fail|error", "query": "ok|error"}
    GET    /beast/{gw}/_store/{apiId}  the spec currently "registered" on that gateway
    DELETE /beast/_store               forget everything (all gateways)

State is kept in a JSON file (app/store.py), so restarting the mock — or redeploying the
container, as long as the volume is mounted — leaves every deployed API where it was.
`DELETE /beast/_store` is the only way to empty it.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import store

router = APIRouter(tags=["beast"])

GATEWAYS = ("ktc", "azure", "prd-ktc", "prd-azure")

OK_COMMON = {"code": 200, "message": "정상처리되었습니다."}

# 배포된 명세와 스위치는 파일에 남는다(app/store.py). 목을 다시 띄워도 올라간 API 가 그대로 있어야
# 화면의 "현재 등록본"·"신규 배포" 판정이 어제와 같은 답을 낸다.
_STORE_KEY = "beast_store"
_CTL_KEY = "beast_ctl"

# gateway -> apiId -> spec
_store: dict[str, dict[str, dict[str, Any]]] = {gw: {} for gw in GATEWAYS}
_store.update({gw: specs for gw, specs in store.load(_STORE_KEY, {}).items() if gw in GATEWAYS})

# gateway -> switches
_ctl: dict[str, dict[str, str]] = {gw: {"deploy": "ok", "query": "ok"} for gw in GATEWAYS}
for _gw, _switches in store.load(_CTL_KEY, {}).items():
    if _gw in GATEWAYS:
        _ctl[_gw].update(_switches)


def _save_store() -> None:
    store.save(_STORE_KEY, _store)


def _save_ctl() -> None:
    store.save(_CTL_KEY, _ctl)


class CtlReq(BaseModel):
    deploy: Literal["ok", "fail", "error"] | None = None
    query: Literal["ok", "error"] | None = None


def _gateway(gw: str) -> str:
    if gw not in GATEWAYS:
        raise HTTPException(status_code=404, detail=f"unknown gateway: {gw} (use one of {', '.join(GATEWAYS)})")
    return gw


TB_GATEWAYS = ("ktc", "azure")


def find_deployed(path: str, method: str, gateways: tuple[str, ...] = TB_GATEWAYS):
    """Find a deployed spec whose inbound path and method match this call.

    The TB domain uses this to refuse calls to APIs that were never deployed, so the screens
    show the same "deploy first, then call" order a real gateway enforces.

    `in` is the inbound path the gateway publishes (API_PATH) and `meth` the method, both taken
    straight from the deploy payload. A `{param}` segment matches any single segment, so
    /messages/{msgId} answers a call to /messages/42.

    Returns (gateway, apiId, spec) or None.
    """
    wanted = _segments(path)
    for gw in gateways:
        for api_id, spec in _store[gw].items():
            if str(spec.get("meth", "")).upper() != method.upper():
                continue
            if _path_matches(_segments(str(spec.get("in", ""))), wanted):
                return gw, api_id, spec
    return None


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _path_matches(pattern: list[str], actual: list[str]) -> bool:
    if len(pattern) != len(actual):
        return False
    return all(p.startswith("{") and p.endswith("}") or p == a for p, a in zip(pattern, actual))


def _transport_error(op: str) -> JSONResponse:
    # A non-2xx status makes the Java RestTemplate throw, which is what a real outage looks like.
    return JSONResponse(status_code=500, content={"error": f"[mock] {op} 연동 실패 흉내"})


# --------------------------------------------------------------------- control
# Registered before the gateway routes so "_ctl" / "_store" are never read as a gateway name.

@router.get("/beast/_ctl")
def get_ctl() -> dict[str, Any]:
    return {gw: {**_ctl[gw], "apiIds": sorted(_store[gw])} for gw in GATEWAYS}


@router.put("/beast/_ctl/{gw}")
def put_ctl(gw: str, req: CtlReq) -> dict[str, str]:
    _gateway(gw)
    if req.deploy is not None:
        _ctl[gw]["deploy"] = req.deploy
    if req.query is not None:
        _ctl[gw]["query"] = req.query
    _save_ctl()
    return _ctl[gw]


@router.delete("/beast/_store")
def reset_store() -> dict[str, str]:
    for gw in GATEWAYS:
        _store[gw].clear()
        _ctl[gw].update({"deploy": "ok", "query": "ok"})
    _save_store()
    _save_ctl()
    return {"result": "cleared"}


@router.get("/beast/{gw}/_store/{api_id}")
def get_stored(gw: str, api_id: str) -> dict[str, Any]:
    spec = _store[_gateway(gw)].get(api_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"{api_id} is not registered on {gw}")
    return spec


# --------------------------------------------------------------------- BEAST

@router.post("/beast/{gw}/apilink/v1/api/apiDply")
def api_deploy(gw: str, spec: dict[str, Any] = Body(...)):
    _gateway(gw)
    mode = _ctl[gw]["deploy"]
    if mode == "error":
        return _transport_error("배포")
    if mode == "fail":
        # Same shape BEAST uses when it refuses a spec, e.g. an unregistered sysId.
        return {"common": {"code": 400, "message": "[mock] 배포 실패 흉내 — sysId 가 등록되지 않은 시스템입니다."}}

    api_id = spec.get("apiId")
    if not api_id:
        return {"common": {"code": 400, "message": "[mock] apiId 가 없습니다."}}

    if spec.get("dplyType") == "DEL":
        _store[gw].pop(api_id, None)
    else:
        _store[gw][api_id] = spec
    _save_store()
    return {"common": OK_COMMON}


@router.get("/beast/{gw}/apilink/v1/api/getApiDplyById")
def get_api_deploy_by_id(gw: str, api_id: str = Query(..., alias="apiId")):
    _gateway(gw)
    if _ctl[gw]["query"] == "error":
        return _transport_error("조회")

    spec = _store[gw].get(api_id)
    if spec is None:
        return {"common": OK_COMMON, "data": {}}
    return {"common": OK_COMMON, "data": {"value": spec}}
