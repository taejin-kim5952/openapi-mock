from fastapi import FastAPI

from app.routers import beast, ldap, mail, psso, shub_verify, tb_domain

app = FastAPI(
    title="openapi-mock",
    description="Local mock server for hard-to-reach SHUB / external APIs used by openapi-ptl and openapi-mng-dev.",
    version="0.1.0",
)

app.include_router(ldap.router)
app.include_router(psso.router)
app.include_router(shub_verify.router)
app.include_router(mail.router)
# openapi-mng-dev-jdk21-new ext.apiops — BEAST gateway and the TB API domain (docs/08 §7, §8-6, §9-6)
app.include_router(beast.router)
app.include_router(tb_domain.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
