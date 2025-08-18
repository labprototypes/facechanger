# apps/api/app/routes/internal.py
import os
import boto3
from fastapi import APIRouter, HTTPException
from ..store import FRAMES, SKU_FRAMES
from typing import List, Optional, Dict, Any
import time
from pydantic import BaseModel
from fastapi import HTTPException
import uuid
from ..store import (
    FRAMES, SKU_BY_CODE, SKU_FRAMES, register_generation, set_generation_prediction,
    add_generation_results, set_generation_status, set_frame_mask_key, list_frames_for_sku_id
)
from ..s3util import public_url_for_key, presigned_get_for_key  # если нет – см. примечание ниже
from pydantic import BaseModel

router = APIRouter(prefix="/internal", tags=["internal"])

S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")

class GenerationIn(BaseModel):
    status: Optional[str] = None        # "QUEUED" | "RUNNING" | "DONE" | "FAILED"
    output_keys: Optional[List[str]] = None  # список s3-ключей с результатами (если уже есть)
    meta: Optional[Dict[str, Any]] = None    # любые доп. поля от воркера
    error: Optional[str] = None              # текст ошибки, если упало

def s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=AWS_KEY or None,
        aws_secret_access_key=AWS_SECRET or None,
    )


def public_url(key: str) -> str:
    # если кастомный endpoint (S3-совместимое хранилище)
    if S3_ENDPOINT:
        return f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{key}"
    # обычный AWS S3 с регионом
    if S3_REGION:
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
    # фоллбэк на us-east-1 стиль
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"


def presigned_get_url(key: str, expires: int = 3600) -> str:
    cli = s3()
    return cli.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


@router.get("/sku/{sku_id}/frames")
def internal_frames_for_sku(sku_id: str):
    ids = SKU_FRAMES.get(sku_id, [])
    return {"frames": [{"id": fid} for fid in ids if fid in FRAMES]}


@router.get("/frame/{frame_id}")
def internal_frame_info(frame_id: str):
    fr = FRAMES.get(frame_id)
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")

    key = fr.get("original_key")
    if not key:
        raise HTTPException(status_code=400, detail="frame has no original_key")

    return {
        "id": fr["id"],
        "sku": fr.get("sku"),
        "name": fr.get("name"),
        "original_key": key,
        "original_url": presigned_get_url(key),  # нужно воркеру
        "public_url": public_url(key),
        "head": fr.get("head"),
    }

class GenReq(BaseModel):
    params: dict | None = None

@router.post("/frame/{frame_id}/generation")
def internal_register_generation(frame_id: int, body: GenReq | None = None):
    fr = FRAMES.get(frame_id)
    if not fr:
        return JSONResponse({"error":"frame_not_found"}, status_code=404)
    g = register_generation(frame_id, (body.params if body else None) or {})
    return {"id": g["id"]}

class PredReq(BaseModel):
    prediction_id: str

@router.post("/generation/{gen_id}/prediction")
def internal_attach_prediction(gen_id: str, body: PredReq):
    set_generation_prediction(gen_id, body.prediction_id)
    return {"ok": True}

class ResultsReq(BaseModel):
    urls: list[str]

@router.post("/generation/{gen_id}/result")
def internal_add_results(gen_id: str, body: ResultsReq):
    add_generation_results(gen_id, body.urls)
    return {"ok": True}

class StatusReq(BaseModel):
    status: str
    error: str | None = None

@router.post("/generation/{gen_id}/status")
def internal_set_status(gen_id: str, body: StatusReq):
    set_generation_status(gen_id, body.status, body.error)
    return {"ok": True}

class MaskReq(BaseModel):
    mask_key: str

@router.post("/frame/{frame_id}/mask")
def internal_set_mask(frame_id: int, body: MaskReq):
    set_frame_mask_key(frame_id, body.mask_key)
    return {"ok": True"}
