import os
from pydantic import BaseModel

class Settings(BaseModel):
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./local.db")
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    s3_endpoint: str | None = os.environ.get("S3_ENDPOINT")
    s3_region: str | None = os.environ.get("S3_REGION")
    s3_bucket: str = os.environ.get("S3_BUCKET", "")
    aws_key: str | None = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret: str | None = os.environ.get("AWS_SECRET_ACCESS_KEY")

    replicate_api_token: str = os.environ.get("REPLICATE_API_TOKEN", "")
    replicate_model: str = os.environ.get("REPLICATE_MODEL", "")  # owner/model:version
    replicate_webhook_secret: str = os.environ.get("REPLICATE_WEBHOOK_SECRET", "")

    cors_allow_origins: str = os.environ.get("CORS_ALLOW_ORIGINS", "*")
    api_base_url: str = os.environ.get("API_BASE_URL", os.environ.get("RENDER_EXTERNAL_URL", ""))

settings = Settings()
