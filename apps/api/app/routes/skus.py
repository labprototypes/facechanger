import os, uuid, math
from typing import List, Optional, Dict, Any
import boto3
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from ..store import (
    SKU_BY_CODE, next_sku_id, next_frame_id,
    FRAMES, SKU_FRAMES, SKUS_BY_ID, register_sku,
    register_frame, get_frame, list_frames_for_sku, FRAME_GENERATIONS, GENERATIONS_BY_ID,
    HEADS
)
from ..celery_client import queue_process_sku, queue_process_frame

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
    head_id: Optional[int] = 1  # ссылка на head profile/registry (in-memory HEADS)
    enqueue: bool = True

def _ensure_sku(code: str) -> int:
    if code in SKU_BY_CODE:
        return SKU_BY_CODE[code]
    sid = register_sku(code)
    return sid

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
    """Register frames for SKU and optionally enqueue processing.

    Replaces buggy previous implementation (undefined vars)."""
    if not body.items:
        raise HTTPException(422, "items required")
    if len(body.items) > 10:
        raise HTTPException(422, "maximum 10 items per submit")

    sku_id = _ensure_sku(sku_code)

    frame_ids: List[int] = []
    head_obj = HEADS.get(body.head_id) if body.head_id else None
    head_payload = None
    if head_obj:
        head_payload = {
            "trigger_token": head_obj.get("trigger"),
            "prompt_template": head_obj.get("params", {}).get("prompt_template", "a photo of {token} female model"),
            "model_version": head_obj.get("model_version"),
        }
    for it in body.items:
        fid = register_frame(sku_id, original_key=it.key, head=head_payload)
        frame_ids.append(fid)

    queued = False
    if body.enqueue:
        queue_process_sku(sku_id)
        queued = True
    return {"sku_id": sku_id, "frame_ids": frame_ids, "queued": queued}

@router.get("/{sku_code}")
def sku_view_simple(sku_code: str):
    """Simple SKU view used by legacy frontend call /skus/{code}.
    Returns frames with basic status and generation counts."""
    if sku_code not in SKU_BY_CODE:
        raise HTTPException(404, "sku not found")
    sku_id = SKU_BY_CODE[sku_code]
    frames = list_frames_for_sku(sku_id)
    items: List[Dict[str, Any]] = []
    for fr in frames:
        gens = FRAME_GENERATIONS.get(fr["id"], [])
        items.append({
            "id": fr["id"],
            "original_key": fr.get("original_key"),
            "status": fr.get("status", "queued"),
            "generations": len(gens),
        })
    return {"sku": {"id": sku_id, "code": sku_code}, "frames": items}

@router.get("/{sku_code}/frames")
def list_sku_frames(sku_code: str):
    if sku_code not in SKU_BY_CODE:
        raise HTTPException(404, "sku not found")
    sku_id = SKU_BY_CODE[sku_code]
    frames = list_frames_for_sku(sku_id)
    return {"items": frames}


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
