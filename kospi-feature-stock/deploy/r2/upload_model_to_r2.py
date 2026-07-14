"""
로컬 LightGBM 모델 → Cloudflare R2 업로드
실행 전: Docker 컨테이너에서 모델 파일 복사 필요

  docker cp quant-eye-ml:/models/lgbm ./lgbm_export

실행:
  pip install boto3 python-dotenv
  python deploy/r2/upload_model_to_r2.py --src ./lgbm_export
"""
import argparse
import os
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY"]
R2_SECRET_KEY = os.environ["R2_SECRET_KEY"]
R2_BUCKET     = os.environ.get("R2_BUCKET", "quant-eye-history")

_MODEL_FILES = [
    "entry_model.lgb",
    "risk_model.lgb",
    "entry_calibrator.pkl",
    "risk_calibrator.pkl",
    "feature_columns.json",
    "model_metrics.json",
]


def main(src_dir: str):
    src = Path(src_dir)
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    for fname in _MODEL_FILES:
        local = src / fname
        if not local.exists():
            print(f"  [SKIP] {fname} — 파일 없음")
            continue
        key = f"models/lgbm/{fname}"
        s3.upload_file(str(local), R2_BUCKET, key)
        size_kb = local.stat().st_size // 1024
        print(f"  [OK] {fname} ({size_kb} KB) → s3://{R2_BUCKET}/{key}")

    print("\n✅ R2 모델 업로드 완료")
    print("API 서버 재기동 시 자동으로 다운로드됩니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="./lgbm_export", help="모델 파일 폴더")
    args = parser.parse_args()
    main(args.src)
