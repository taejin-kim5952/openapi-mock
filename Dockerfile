FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 설정값 기본값은 app/config.py의 Settings 클래스 기본값(.env.example과 동일)을 그대로 쓴다.
# 실제 배포에서 값을 바꾸려면 이미지에 .env를 넣지 말고 `docker run -e LDAP_AES_KEY=... -e PSSO_AES_KEY=...`
# 처럼 환경변수로 덮어쓴다(README의 "AES 키" 절 참고 - 여러 연동 시스템과 값이 일치해야 함).

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
