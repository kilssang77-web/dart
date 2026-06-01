from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://biduser:bidpass123@localhost:5432/biddb"
    redis_url: str = "redis://:redispass123@localhost:6379/0"
    secret_key: str = "changeme-super-secret-key-2024"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    first_admin_email: str = "admin@bid.local"
    first_admin_password: str = "admin1234"
    seed_demo_data: bool = True

    g2b_api_key: str = ""
    collect_enabled: bool = False

    ml_models_path: str = "/app/ml_models"
    min_train_samples: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
