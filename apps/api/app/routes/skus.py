import os, uuid
from typing import List, Optional
import boto3
from fastapi import APIRouter
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

HEADS = {
    1: {
        "name": "Маша",
        "trigger_token": "tnkfwm1",
        "prompt_template": "a photo of {token} female model",
    },
    # тут позже добавим другие профили
}

def head_profile_from_id(head_id: Optional[int]):
    return HEADS.get(int(head_id or 1), HEADS[1])

def s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=AWS_KEY or None,
        aws_secret_access_key=AWS_SECRET or None,
    )

def public_url(key: str) -> str:
    # Если используем кастомный S3 endpoint (или хотим path-style), строим так:
    if S3_ENDPOINT:
        return f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{key}"
    # Иначе нормальный региональный virtual-hosted style:
    if S3_REGION:
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
    # Фоллбэк на us-east-1 стиль
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
    head_id: Optional[int] = 1   # по умолчанию "Маша"
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
    # 1) выдаём sku_id (создаём если нет)
    if sku_code in SKU_BY_CODE:
        sku_id = SKU_BY_CODE[sku_code]
    else:
        sku_id = next_sku_id()
        SKU_BY_CODE[sku_code] = sku_id
        SKU_FRAMES[sku_id] = []

    # 2) регистрируем кадры с original_key (воркер сам сделает presigned GET)
    frame_ids = []
    for it in body.items:
        fid = next_frame_id()
        frame_ids.append(fid)
        FRAMES[fid] = {
            "id": fid,
            "sku": {"code": sku_code, "id": sku_id},
            "original_key": it.key,
            "name": it.name,
            # профиль головы (дефолт «Маша»)
            "head": head_profile_from_id(body.head_id),
        }
        SKU_FRAMES[sku_id].append(fid)

    # 3) опционально ставим в очередь
    queued = False
    if body.enqueue and frame_ids:
        task = queue_process_sku(sku_id)
        queued = True

    return {"sku_id": sku_id, "frame_ids": frame_ids, "queued": queued}

# --- Fallback загрузка через backend (multipart) ---
from fastapi import UploadFile, File

@router.post("/{sku_code}/upload")
async def upload_via_api(sku_code: str, files: List[UploadFile] = File(...)):
    cli = s3()
    out = []
    for f in files:
        key = f"uploads/{sku_code}/{uuid.uuid4().hex}_{f.filename}"
        # грузим поток прямо в S3
        cli.upload_fileobj(
            f.file,
            S3_BUCKET,
            key,
            ExtraArgs={"ContentType": f.content_type or "application/octet-stream"},
        )
        out.append({"name": f.filename, "key": key})
    return {"items": out}

@router.get("/{sku_code}")
def get_sku_view(sku_code: str):
    # найти sku_id
    if sku_code not in SKU_BY_CODE:
        return {"sku": {"code": sku_code}, "frames": []}
    sku_id = SKU_BY_CODE[sku_code]

    frames_out = []
    for fid in SKU_FRAMES.get(sku_id, []):
        fr = FRAMES[fid]
        # original
        original_key = fr.get("original_key")
        original_url = public_url(original_key) if original_key else fr.get("original_url")

        # mask
        mask_key = fr.get("mask_key")
        mask_url = public_url(mask_key) if mask_key else None

        frames_out.append({
            "id": fid,
            "original_url": original_url,
            "mask_url": mask_url,
            "variants": fr.get("variants", []),   # [{ url, gen_id }]
            "head": fr.get("head"),
        })

    total = len(frames_out)
    done = sum(1 for f in frames_out if f.get("variants"))
    progress = {"total": total, "ready": done}

    return {"sku": {"code": sku_code, "id": sku_id}, "progress": progress, "frames": frames_out}
