import os, uuid, math
from typing import List, Optional, Dict, Any
import boto3
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from ..store import (
    SKU_BY_CODE, register_sku, register_frame, get_frame, list_frames_for_sku,
    FRAME_GENERATIONS, GENERATIONS_BY_ID, HEADS, delete_frame, delete_sku,
    get_sku_by_code
)
import os
USE_DB = bool(os.environ.get("DATABASE_URL"))
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
    # Frontend may send either 'name' or 'filename'; accept both.
    name: Optional[str] = None
    filename: Optional[str] = None
    type: Optional[str] = None
    size: Optional[int] = None
    def real_name(self) -> str:
        return (self.name or self.filename or "file").replace("/", "_")

class UploadUrlsReq(BaseModel):
    files: List[FileSpec]

class SubmitItem(BaseModel):
    key: str
    name: Optional[str] = None

class SubmitReq(BaseModel):
    items: List[SubmitItem]
    head_id: Optional[int] = 1  # ссылка на head profile/registry (in-memory HEADS)
    enqueue: bool = True
    brand: Optional[str] = None
    # New style options (required by frontend)
    hair_style: Optional[str] = None
    hair_color: Optional[str] = None
    eye_color: Optional[str] = None

def _ensure_sku(code: str, brand: Optional[str] = None) -> int:
    if USE_DB:
        sku = get_sku_by_code(code)
        if sku:
            return sku["id"]
        return register_sku(code, brand=brand)
    if code in SKU_BY_CODE:
        return SKU_BY_CODE[code]
    return register_sku(code, brand=brand)

@router.post("/{sku_code}/upload-urls")
def create_upload_urls(sku_code: str, body: UploadUrlsReq):
    cli = s3()
    out = []
    if not body.files:
        raise HTTPException(422, "files required")
    for f in body.files:
        fname = f.real_name()
        key = f"uploads/{sku_code}/{uuid.uuid4().hex}_{fname}"
        put_url = cli.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": key,
                "ContentType": f.type or "application/octet-stream",
            },
            ExpiresIn=3600,
        )
        out.append({"name": fname, "key": key, "put_url": put_url, "public_url": public_url(key)})
    return {"items": out}

@router.post("/{sku_code}/submit")
def submit_sku(sku_code: str, body: SubmitReq):
    """Register frames for SKU and optionally enqueue processing.

    Replaces buggy previous implementation (undefined vars)."""
    if not body.items:
        raise HTTPException(422, "items required")
    if len(body.items) > 10:
        raise HTTPException(422, "maximum 10 items per submit")

    sku_id = _ensure_sku(sku_code, brand=body.brand)

    # Validate required style fields
    if not body.head_id:
        raise HTTPException(422, "head_id is required")
    if not body.hair_style or not body.hair_color or not body.eye_color:
        raise HTTPException(422, "hair_style, hair_color and eye_color are required")

    # Resolve / persist head_profile for DB mode
    if USE_DB and body.head_id:
        head_obj = HEADS.get(body.head_id)
        if head_obj:
            from ..database import get_session
            from sqlalchemy import select
            from .. import models
            sess = get_session()
            try:
                trig = head_obj.get("trigger")
                hp = None
                if trig:
                    hp = sess.execute(select(models.HeadProfile).where(models.HeadProfile.trigger_token == trig)).scalar_one_or_none()
                if not hp and head_obj.get("name"):
                    hp = sess.execute(select(models.HeadProfile).where(models.HeadProfile.name == head_obj.get("name"))).scalar_one_or_none()
                if hp:
                    sku_row = sess.get(models.SKU, int(sku_id))
                    if sku_row and sku_row.head_profile_id != hp.id:
                        sku_row.head_profile_id = hp.id
                        sess.add(sku_row); sess.commit()
            finally:
                sess.close()

    head_obj = HEADS.get(body.head_id) if body.head_id else None
    head_payload = None
    if head_obj and not USE_DB:
        head_payload = {
            "trigger_token": head_obj.get("trigger"),
            "prompt_template": head_obj.get("prompt_template") or "a photo of {token} female model",
            "model_version": head_obj.get("model_version"),
            "params": head_obj.get("params") or {},
        }

    frame_ids: List[int] = []
    # Compose style params to persist into pending_params for each frame
    style_params = {
        "hair_style": body.hair_style,
        "hair_color": body.hair_color,
        "eye_color": body.eye_color,
        # bump prompt_strength default to 0.9 unless user changes later
        "prompt_strength": 0.9,
    }
    from ..store import replace_frame_pending_params as _set_pending
    for it in body.items:
        fid = register_frame(sku_id, original_key=it.key, head=head_payload)
        try:
            _set_pending(fid, style_params)
        except Exception:
            pass
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
    if USE_DB:
        sku = get_sku_by_code(sku_code)
        if not sku:
            raise HTTPException(404, "sku not found")
        sku_id = sku["id"]
    else:
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
    # include brand if available (DB or in-memory)
    brand = None
    if USE_DB:
        sku = get_sku_by_code(sku_code)
        brand = sku.get("brand") if sku else None
    else:
        sid = SKU_BY_CODE.get(sku_code)
        sku = None
        if sid:
            from ..store import SKUS_BY_ID as _SKUS
            sku = _SKUS.get(sid)
        brand = sku.get("brand") if sku else None
    return {"sku": {"id": sku_id, "code": sku_code, "brand": brand}, "frames": items}

@router.get("/{sku_code}/frames")
def list_sku_frames(sku_code: str):
    if USE_DB:
        sku = get_sku_by_code(sku_code)
        if not sku:
            raise HTTPException(404, "sku not found")
        sku_id = sku["id"]
    else:
        if sku_code not in SKU_BY_CODE:
            raise HTTPException(404, "sku not found")
        sku_id = SKU_BY_CODE[sku_code]
    frames = list_frames_for_sku(sku_id)
    return {"items": frames, "brand": (get_sku_by_code(sku_code) or {}).get("brand")}

@router.delete("/{sku_code}")
def delete_sku_public(sku_code: str):
    if USE_DB:
        sku = get_sku_by_code(sku_code)
        if not sku:
            raise HTTPException(404, "sku not found")
        delete_sku(sku_code)
    else:
        if sku_code not in SKU_BY_CODE:
            raise HTTPException(404, "sku not found")
        delete_sku(sku_code)
    return {"ok": True, "deleted": sku_code}

@router.delete("/{sku_code}/frame/{frame_id}")
def delete_frame_public(sku_code: str, frame_id: int):
    if USE_DB:
        sku = get_sku_by_code(sku_code)
        if not sku:
            raise HTTPException(404, "sku not found")
        fr = get_frame(int(frame_id))
        if not fr:
            raise HTTPException(404, "frame not found")
        if fr.get("sku", {}).get("id") != sku["id"]:
            raise HTTPException(400, "frame does not belong to sku")
    else:
        if sku_code not in SKU_BY_CODE:
            raise HTTPException(404, "sku not found")
        fr = get_frame(int(frame_id))
        if not fr:
            raise HTTPException(404, "frame not found")
        if fr.get("sku", {}).get("id") != SKU_BY_CODE[sku_code]:
            raise HTTPException(400, "frame does not belong to sku")
    delete_frame(int(frame_id))
    return {"ok": True, "deleted_frame_id": int(frame_id)}


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
