"""
로컬 LightGBM 모델 -> Cloudflare R2 업로드.
업로드 전 기존 모델 파일을 삭제하여 R2 스토리지 중복 방지.

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
_MODEL_PREFIX = "models/lgbm/"


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _print_r2_stats(s3) -> None:
    resp = s3.list_objects_v2(Bucket=R2_BUCKET)
    total = sum(o["Size"] for o in resp.get("Contents", []))
    count = len(resp.get("Contents", []))
    print(f"\nR2 현재 사용량: {total/1024/1024:.1f} MB ({count}개 객체) / 10,000 MB 무료")


def main(src_dir: str) -> None:
    src = Path(src_dir)
    s3 = _r2_client()

    # 업로드 전 현황 출력
    _print_r2_stats(s3)

    # 기존 모델 파일 삭제 (같은 키를 덮어쓰면 중복 없음, but 명시적으로 처리)
    existing = s3.list_objects_v2(Bucket=R2_BUCKET, Prefix=_MODEL_PREFIX)
    old_keys = [o["Key"] for o in existing.get("Contents", [])
                if any(o["Key"].endswith(f) for f in _MODEL_FILES)]
    if old_keys:
        s3.delete_objects(
            Bucket=R2_BUCKET,
            Delete={"Objects": [{"Key": k} for k in old_keys]},
        )
        print(f"  [삭제] 구버전 {len(old_keys)}개 제거")

    # 신규 업로드
    uploaded = 0
    for fname in _MODEL_FILES:
        local = src / fname
        if not local.exists():
            print(f"  [SKIP] {fname} — 파일 없음")
            continue
        key = f"{_MODEL_PREFIX}{fname}"
        s3.upload_file(str(local), R2_BUCKET, key)
        size_kb = local.stat().st_size // 1024
        print(f"  [OK]   {fname} ({size_kb} KB) -> s3://{R2_BUCKET}/{key}")
        uploaded += 1

    print(f"\n업로드 완료: {uploaded}개")
    _print_r2_stats(s3)
    print("API 서버 재기동 시 자동으로 다운로드됩니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="./lgbm_export", help="모델 파일 폴더")
    args = parser.parse_args()
    main(args.src)
