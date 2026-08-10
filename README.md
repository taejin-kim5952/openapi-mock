# openapi-mock

`openapi-ptl`이 연동하는 외부(SHUB) API 중 로컬에서 연결이 어려운 것을 대체하는 **Python FastAPI 목 서버**입니다.

프론트(`openapi-ptl-ui`)는 변경하지 않습니다. 백엔드 Feign URL만 이 서버로 향하게 합니다.

## 현재 지원 API

| 외부 API | Method / Path | 비고 |
|----------|---------------|------|
| SHUB LDAP LoginProfile (OIF_24006) | `POST /ldap/v3.1/loginprofile` | AES-256/GCM 암복호화 (Java `Aes256GcmSupport` 호환) |
| PSSO memberLogin (openapi-mng-dev) | `POST /psso/v2.0/psso_memberLogin` | AES/CBC/PKCS5(zero IV) 암복호화 (Java `CommonFunc.aesEncode/aesDecode` 호환) |

공통:

- `GET /health` — 기동 확인
- `GET /ldap/v3.1/loginprofile/users` — 목 계정 ID 목록 (비밀번호 제외)
- `GET /psso/v2.0/psso_memberLogin/users` — 목 PSSO 계정 ID 목록 (비밀번호 제외)

## 요구 사항

- Python 3.11+
- (연동 시) `openapi-ptl` local 프로파일

## 설치 & 기동

```bash
cd D:\workspace_aplink\openapi-mock
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
```

브라우저/헬스체크: <http://localhost:8090/health>  
Swagger: <http://localhost:8090/docs>

## AES 키

백엔드 `ptl.ldap.aes.key` 와 **반드시 동일**해야 합니다.

기본값 (`app-config.yml` / `.env.example`):

```text
SEQNUM01KG118K65MZ69NM8GMGE0XE5W
```

환경 변수 `LDAP_AES_KEY` 로 덮어쓸 수 있습니다.

## 목 LDAP 계정

[`app/fixtures/ldap_users.yaml`](app/fixtures/ldap_users.yaml)

| login_id | login_pwd |
|----------|-----------|
| `ldapuser01` | `ldapPass01!` |
| `ldapuser02` | `ldapPass02!` |

실패 케이스는 fixtures에 없는 ID/PWD를 보내면 `returncode != "1"` 응답이 나갑니다.

## openapi-ptl 로컬 연결

[`application-local.yml`](../openapi-ptl/src/main/resources/application-local.yml)에 이미 설정되어 있습니다:

```yaml
ptl:
  ldap:
    url: http://localhost:8090
```

`project.security.ldap.enabled=true`(local 기본) 상태에서:

1. 목 서버 기동 (8090)
2. `openapi-ptl` local 기동 (8080)
3. `openapi-ptl-ui` 기동 (5173)
4. 로그인 모달 → **LDAP** 탭 → 위 목 계정으로 로그인
5. 1차 성공 후 **OTP** 단계로 이동하는지 확인

BFF 확인: `GET http://localhost:8080/v1/auth/ldap/bff` → `ready: true`, `loginProcessingUrl` 존재.

## 수동 검증 (목 서버만)

```bash
# 1) health
curl http://localhost:8090/health

# 2) fixture users
curl http://localhost:8090/ldap/v3.1/loginprofile/users
```

암호화된 LoginProfile 바디는 백엔드 `LdapLoginService`가 만들어 보내므로, E2E는 위 LDAP UI/백엔드 경로로 확인하는 것이 가장입니다.

암호 유틸 단독 스모크:

```bash
python -c "from app.crypto.aes_gcm import encrypt, decrypt; k='SEQNUM01KG118K65MZ69NM8GMGE0XE5W'; c=encrypt('hello', k); assert decrypt(c, k)=='hello'; print('ok', c[:20]+'...')"
```

## openapi-mng-dev PSSO 연결

[`config/local/application-local.yml`](../openapi-mng-dev/src/main/resources/config/local/application-local.yml)에 이미 설정되어 있습니다:

```yaml
new:
  psso:
    api:
      member:
        logincheck: http://localhost:8090/psso/v2.0/psso_memberLogin
```

`PSSO_AES_KEY`(openapi-mng-dev 실행 설정의 환경변수, `psso.aes.key`로 주입됨)는 이 서버의 `PSSO_AES_KEY`(`.env`)와 **반드시 동일**해야 합니다. 기본값은 `PSSOMOCK25OVMC6CV13PC97OBEWX5FYE` (32자, AES-256).

목 PSSO 계정: [`app/fixtures/psso_users.yaml`](app/fixtures/psso_users.yaml)

| login_id | login_pwd |
|----------|-----------|
| `pssouser01` | `pssoPass01!` |
| `pssouser02` | `pssoPass02!` |

## 확장

같은 앱에 라우터를 추가하면 됩니다.

- `app/routers/two_factor.py`

`app/main.py`에서 `include_router` 하면 됩니다.

## 포트

| 서비스 | 포트 |
|--------|------|
| openapi-mock | **8090** |
| openapi-ptl | 8080 |
| openapi-ptl-ui | 5173 |
