import boto3, uuid, os, httpx
from datetime import datetime
from .config import settings

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        region_name=settings.s3_region or None,
        aws_access_key_id=settings.aws_key or None,
        aws_secret_access_key=settings.aws_secret or None,
    )

def make_upload_key(sku: str, filename: str) -> str:
    today = datetime.utcnow().strftime("%Y/%m/%d")
    ext = filename.split(".")[-1].lower()
    uid = uuid.uuid4().hex[:12]
    return f"uploads/{sku}/{today}/{uid}.{ext}"

def mask_key(sku: str, frame_id: int) -> str:
    return f"masks/{sku}/{frame_id}.png"

def output_key(sku: str, frame_id: int, pred_id: str, index: int) -> str:
    return f"outputs/{sku}/{frame_id}/{pred_id}_{index}.png"

def presign_put(key: str, content_type: str = "application/octet-stream", expires=3600) -> str:
    return s3_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )

def public_url(key: str) -> str:
    return f"https://{settings.s3_bucket}.s3.amazonaws.com/{key}"

async def upload_from_url(key: str, url: str):
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url)
        r.raise_for_status()
        s3_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=r.content, ContentType="image/png")
    return public_url(key)
