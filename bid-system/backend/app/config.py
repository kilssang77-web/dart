from pydantic_settings import BaseSettings
from functools import lru_cache

_DEV_SECRET = "changeme-super-secret-key-2024"


class Settings(BaseSettings):
    database_url: str = "postgresql://biduser:bidpass123@localhost:5432/biddb"
    redis_url: str = "redis://:redispass123@localhost:6379/0"
    secret_key: str = _DEV_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7일 — 업무 중 자동 로그아웃 방지

    first_admin_email: str = "admin@bid.local"
    first_admin_password: str = "admin1234"
    force_reset_admin_password: bool = False  # true 시 재시작 때 DB 비밀번호를 .env 값으로 강제 동기화
    seed_demo_data: bool = True

    g2b_api_key: str = ""
    kiscon_api_key: str = ""     # 공공데이터포털 KISCON 시공능력평가 API 키 (없으면 bid_results 집계만 수행)
    collect_enabled: bool = False
    inpo21c_cookie: str = ""
    inpo21c_id: str = ""
    inpo21c_pw: str = ""

    # CORS: "*" = 전체 허용 (개발), 프로덕션은 "https://app.example.com,https://admin.example.com"
    cors_origins: str = "*"

    ml_models_path: str = "/app/ml_models"
    min_train_samples: int = 50

    @property
    def is_default_secret(self) -> bool:
        return self.secret_key == _DEV_SECRET

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()

