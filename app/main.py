from fastapi import FastAPI

from app.routers import ldap, mail, psso, shub_verify

app = FastAPI(
    title="openapi-mock",
    description="Local mock server for hard-to-reach SHUB / external APIs used by openapi-ptl and openapi-mng-dev.",
    version="0.1.0",
)

app.include_router(ldap.router)
app.include_router(psso.router)
app.include_router(shub_verify.router)
app.include_router(mail.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
