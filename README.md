# openapi-mock

`openapi-ptl`이 연동하는 외부(SHUB) API 중 로컬에서 연결이 어려운 것을 대체하는 **Python FastAPI 목 서버**입니다.

프론트(`openapi-ptl-ui`)는 변경하지 않습니다. 백엔드 Feign URL만 이 서버로 향하게 합니다.

## 현재 지원 API

| 외부 API | Method / Path | 비고 |
|----------|---------------|------|
| SHUB LDAP LoginProfile (OIF_24006) | `POST /ldap/v3.1/loginprofile` | AES-256/GCM 암복호화 (Java `Aes256GcmSupport` 호환) |
| PSSO memberLogin (openapi-mng-dev) | `POST /psso/v2.0/psso_memberLogin` | AES/CBC/PKCS5(zero IV) 암복호화 (Java `CommonFunc.aesEncode/aesDecode` 호환) |
| BEAST 게이트웨이 배포 (openapi-mng-dev-jdk21-new) | `POST /beast/{gw}/apilink/v1/api/apiDply` | 받은 명세를 `apiId` 별로 저장. `{gw}` = `ktc` · `azure` · `prd-ktc` · `prd-azure` |
| BEAST 게이트웨이 조회 (openapi-mng-dev-jdk21-new) | `GET /beast/{gw}/apilink/v1/api/getApiDplyById?apiId=` | 있으면 `data.value`, 없으면 200 + 빈 `data`(신규) |
| TB API 도메인 (openapi-mng-dev-jdk21-new 테스트 화면) | `ANY /tbdomain/**` | **TB 게이트웨이에 배포된 API 만** 답한다. KT 공통 응답 형식으로 답하고, 받은 요청을 `response.echo` 로 돌려줌 |

### BEAST · TB 도메인 (openapi-mng-dev-jdk21-new `ext.apiops`)

API 배포 프로세스(TB 배포 → 테스트 → 운영 배포)를 로컬에서 시험하기 위한 목이다.
설계: `openapi-mng-dev-jdk21-new/docs/08_API_DEPLOY_PROCESS_DESIGN.md` §7 · §8-6 · §9-6.
**상태는 파일에 남는다** — 게이트웨이에 배포된 명세와 흉내 스위치는 `STATE_FILE` 이 가리키는
JSON 파일에 저장된다. 목 서버를 다시 띄워도 올라간 API 가 그대로 있다. 비우려면 `DELETE /beast/_store`.

| 환경 | 파일 위치 | 유지되나 |
|---|---|---|
| 로컬 | `openapi-mock/data/state.json` (기본값, `STATE_FILE` 로 변경) | 재기동해도 유지 |
| 도커 | `/data/state.json` — 볼륨 `openapi-mock-data` 를 `/data` 에 마운트 | 재배포해도 유지 |

> 도커에서 **볼륨을 마운트하지 않으면** 컨테이너를 지울 때 배포 기록이 함께 사라진다.
> Jenkinsfile 의 `-v ${DATA_VOLUME}:/data` 가 그 역할을 한다. 수동으로 띄울 때도 빠뜨리지 말 것.

API Manager 로컬 설정(`config/local/application-local.yml`)에서 주소를 이 서버로 돌린다.

| 대상 | 설정 키 | 목 주소 |
|---|---|---|
| `TB_KTC` | `bstgw.api.tb.url` | `http://127.0.0.1:8090/beast/ktc` |
| `TB_AZURE` | `bstgw.api.new.tb.url` | `http://127.0.0.1:8090/beast/azure` |
| `PRD_KTC` | `bstgw.api.prd.url` | `http://127.0.0.1:8090/beast/prd-ktc` |
| `PRD_AZURE` | `bstgw.api.new.prd.url` | `http://127.0.0.1:8090/beast/prd-azure` |
| 테스트 도메인 | `gateway.al.tbUrl` | `http://127.0.0.1:8090/tbdomain` |

#### 배포한 API 만 호출된다

테스트 도메인은 **TB 게이트웨이(`ktc` · `azure`)에 배포된 명세**와 맞는 호출에만 답한다.
배포 전문의 인입 경로(`in`)와 Method(`meth`)로 맞춰 보고, 없으면 404 로 거절한다.

```
POST /tbdomain/psso/v1.0/CAPRI_psso_defaultJoin
  → 404  "[mock] 배포되지 않은 API 입니다 - POST /psso/... TB 배포를 먼저 하세요."

(TB 배포 후 같은 호출)
  → 200  response.echo.deployedOn = {"gateway":"ktc","apiId":"psso_defaultJoin_v1.0"}
```

- 실제 게이트웨이도 배포된 것만 라우팅한다. 화면이 가르치는 순서(TB 배포 → 테스트)를 목에서도 그대로 겪게 하려는 것이다.
- 경로 변수는 한 조각을 덮는다. `/messages/{msgId}` 로 배포했으면 `/messages/42` 가 걸린다.
- 배포와 무관하게 아무 경로나 받게 하려면 `PUT /tbdomain/_ctl {"require_deploy": false}`.
- 응답의 `response.echo.deployedOn` 으로 **어느 게이트웨이의 어느 apiId 에 걸렸는지** 확인할 수 있다.

실패 흉내 (조작용 주소 — 실제 BEAST 에는 없음):

| 흉내 | 요청 | 목의 응답 → Java 가 받는 결과 |
|---|---|---|
| 배포 실패 (BEAST 가 거절) | `PUT /beast/_ctl/{gw}` `{"deploy":"fail"}` | HTTP 200 + `common.code 400` → `NK` |
| 배포 연동 실패 | `PUT /beast/_ctl/{gw}` `{"deploy":"error"}` | HTTP 500 → `ERR` |
| 조회 연동 실패 | `PUT /beast/_ctl/{gw}` `{"query":"error"}` | HTTP 500 → v2 가 배포를 중단 |
| 정상으로 | `PUT /beast/_ctl/{gw}` `{"deploy":"ok","query":"ok"}` | |
| 현황 · 저장된 명세 | `GET /beast/_ctl` · `GET /beast/{gw}/_store/{apiId}` | 롤백 확인에 쓴다 |
| 전부 비우기 | `DELETE /beast/_store` | |
| 테스트 도메인 실패 · 시간 초과 | `PUT /tbdomain/_ctl` `{"mode":"fail","status":500}` / `{"mode":"timeout","delay_ms":35000}` | |
| 테스트 도메인 정상으로 | `DELETE /tbdomain/_ctl` | 배포 확인도 켜진 상태로 돌아간다 |
| 배포 확인 끄기 | `PUT /tbdomain/_ctl` `{"require_deploy":false}` | 배포하지 않은 경로도 답한다(예전 동작) |

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
