FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/ml_models

EXPOSE 8000

# WORKERS=1: Render 무료 512MB 환경, WORKERS=2: 로컬/유료 환경
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-2}
