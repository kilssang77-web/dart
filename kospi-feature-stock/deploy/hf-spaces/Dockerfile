FROM python:3.12-slim

WORKDIR /app

# CPU-only torch (GPU 버전 대비 ~1.2GB 절약)
RUN pip install --no-cache-dir \
    torch==2.3.0 --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn[standard]==0.30.1 \
    lightgbm==4.3.0 \
    scikit-learn==1.4.2 \
    sentence-transformers==3.0.1 \
    transformers>=4.40.0 \
    pandas==2.2.2 \
    numpy==1.26.4 \
    asyncpg==0.29.0 \
    pgvector==0.2.5 \
    httpx==0.27.0 \
    orjson==3.10.3 \
    joblib==1.4.2 \
    python-dotenv==1.0.1

# ML 서비스 소스 복사
COPY services/ml ./ml
COPY services/analyzer ./analyzer

# 모델 파일 복사 (빌드 시 포함 or 런타임 마운트)
COPY models/ ./models/

# HF Spaces는 7860 포트 사용
EXPOSE 7860

COPY deploy/hf-spaces/app.py ./app.py

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
