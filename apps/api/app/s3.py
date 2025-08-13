import boto3
from .config import settings

_session = boto3.session.Session(
    aws_access_key_id=settings.aws_key,
    aws_secret_access_key=settings.aws_secret,
    region_name=settings.s3_region,
)

s3 = _session.client("s3", endpoint_url=settings.s3_endpoint)

def presign_put(key: str, content_type: str = "image/jpeg", expires: int = 3600):
    return s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )

def public_url(key: str) -> str:
    return f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"
