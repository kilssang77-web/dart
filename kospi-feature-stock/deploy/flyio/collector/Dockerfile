FROM python:3.12-slim

WORKDIR /app

# 의존성 설치 (캐시 레이어)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# 헬스체크용 경량 HTTP 서버 (UptimeRobot 핑 대상)
COPY healthcheck.py .

CMD ["python", "-u", "main.py"]
