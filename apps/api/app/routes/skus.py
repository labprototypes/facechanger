import os, uuid
from typing import List, Optional
import boto3
from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from ..store import (
    SKU_BY_CODE, next_sku_id, next_frame_id,
    FRAMES, SKU_FRAMES
)
from ..celery_client import queue_process_sku

router = APIRouter(prefix="/skus", tags=["skus"])

S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")

def s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=AWS_KEY or None,
        aws_secret_access_key=AWS_SECRET or None,
    )

def public_url(key: str) -> str:
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"

class FileSpec(BaseModel):
    name: str
    type: Optional[str] = None
    size: Optional[int] = None

class UploadUrlsReq(BaseModel):
    files: List[FileSpec]

class SubmitItem(BaseModel):
    key: str
    name: Optional[str] = None

class SubmitReq(BaseModel):
    items: List[SubmitItem]
    head_id: Optional[int] = 1
    enqueue: bool = True

@router.post("/{sku_code}/upload-urls")
def create_upload_urls(sku_code: str, body: UploadUrlsReq):
    cli = s3()
    out = []
    for f in body.files:
        key = f"uploads/{sku_code}/{uuid.uuid4().hex}_{f.name}"
        put_url = cli.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": key,
                "ContentType": f.type or "application/octet-stream",
            },
            ExpiresIn=3600,
        )
        out.append({"name": f.name, "key": key, "put_url": put_url, "public_url": public_url(key)})
    return {"items": out}

@router.post("/{sku_code}/submit")
def submit_sku(sku_code: str, body: SubmitReq):
    if sku_code in SKU_BY_CODE:
        sku_id = SKU_BY_CODE[sku_code]
    else:
        sku_id = next_sku_id()
        SKU_BY_CODE[sku_code] = sku_id
        SKU_FRAMES[sku_id] = []

    frame_ids = []
    for it in body.items:
        fid = next_frame_id()
        frame_ids.append(fid)
        FRAMES[fid] = {
            "id": fid,
            "sku": {"code": sku_code, "id": sku_id},
            "original_key": it.key,
            "head": {
                "trigger_token": "tnkfwm1",
                "prompt_template": "a photo of {token} female model",
            },
            "variants": [],
        }
        SKU_FRAMES[sku_id].append(fid)

    queued = False
    if body.enqueue and frame_ids:
        queue_process_sku(sku_id)
        queued = True

    return {"sku_id": sku_id, "frame_ids": frame_ids, "queued": queued}

@router.post("/{sku_code}/upload")
async def upload_via_api(sku_code: str, files: List[UploadFile] = File(...)):
    cli = s3()
    out = []
    for f in files:
        key = f"uploads/{sku_code}/{uuid.uuid4().hex}_{f.filename}"
        cli.upload_fileobj(
            f.file,
            S3_BUCKET,
            key,
            ExtraArgs={"ContentType": f.content_type or "application/octet-stream"},
        )
        out.append({"name": f.filename, "key": key})
    return {"items": out}
