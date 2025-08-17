# apps/api/app/routes/internal.py
# -*- coding: utf-8 -*-
"""
Внутренние эндпоинты для воркера.
- /internal/sku/{sku_id}/frames -> список id кадров для SKU
- /internal/frame/{frame_id}    -> подробная инфа по кадру, включая original_url (presigned)
"""

from fastapi import APIRouter, HTTPException
from ..store import list_frames_for_sku, get_frame
from ..s3util import s3_url

router = APIRouter(tags=["internal"])


@router.get("/internal/sku/{sku_id}/frames")
def internal_frames_for_sku(sku_id: str):
    """Вернём список кадров для данного sku_id в формате {"frames":[{"id": "..."}]}."""
    frame_ids = list_frames_for_sku(sku_id) or []
    return {"frames": [{"id": fid} for fid in frame_ids]}


@router.get("/internal/frame/{frame_id}")
def internal_frame_info(frame_id: str):
    """
    Вернём данные по кадру. Главное — отдать presigned GET ссылку в поле `original_url`,
    т.к. воркер ранее падал из-за её отсутствия.
    """
    fr = get_frame(frame_id)
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")

    # --- SKU info (поддержка разных форматов хранения) ---
    sku_code = ""
    sku_id = None
    sku_val = fr.get("sku")
    if isinstance(sku_val, dict):
        sku_code = str(sku_val.get("code") or "")
        sku_id = sku_val.get("id")
    elif sku_val is not None:
        sku_code = str(sku_val)

    # --- S3 key оригинала (поддержка старых ключей) ---
    key = (
        fr.get("original_key")
        or fr.get("key")
        or fr.get("s3_key")
    )
    if not key:
        # Фоллбэк для совсем старых записей: пытаемся собрать путь из имени
        name = fr.get("name")
        if name and sku_code:
            key = f"uploads/{sku_code}/{name}"

    if not key:
        raise HTTPException(status_code=500, detail="frame has no S3 key")

    # --- Presigned GET для оригинала ---
    try:
        original_url = s3_url(key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to build original_url: {e}")

    # Маска по умолчанию — ожидаемый путь (если воркер сам будет её писать)
    mask_key = fr.get("mask_key") or (f"masks/{sku_code}/{fr['id']}.png" if sku_code else None)

    # Профиль головы, если задали при сабмите (Маша по умолчанию хранится в записи кадра)
    head = fr.get("head")

    return {
        "id": fr["id"],
        "sku": {"code": sku_code, "id": sku_id},
        "original_key": key,
        "original_url": original_url,   # <-- то самое поле, которого не хватало воркеру
        "mask_key": mask_key,
        "head": head,
    }
