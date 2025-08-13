from pydantic import BaseModel
import os

class Settings(BaseModel):
    env: str = os.getenv("ENV", "production")
    database_url: str = os.getenv("DATABASE_URL", "")
    redis_url: str = os.getenv("REDIS_URL", "")

    s3_endpoint: str = os.getenv("S3_ENDPOINT", "https://s3.amazonaws.com")
    s3_region: str = os.getenv("S3_REGION", "us-east-1")
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    aws_key: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    aws_secret: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")

    replicate_api_token: str = os.getenv("REPLICATE_API_TOKEN", "")
    replicate_model: str = os.getenv("REPLICATE_MODEL", "")
    replicate_webhook_secret: str = os.getenv("REPLICATE_WEBHOOK_SECRET", "")

    api_base_url: str = os.getenv("API_BASE_URL", "")
    cors_allow_origins: str = os.getenv("CORS_ALLOW_ORIGINS", "*")

settings = Settings()
