# apps/api/app/routes/internal.py
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from ..s3util import s3_url
from fastapi import HTTPException

# мы читаем из простого in-memory стора
# (см. пункт 2: там есть EXACT такие функции/структуры)
from ..store import list_frames_for_sku, get_frame

router = APIRouter(tags=["internal"])

@router.get("/internal/sku/{sku}/frames")
async def internal_frames_for_sku(sku: str) -> Dict[str, Any]:
    """
    Возвращает список кадров по SKU в формате,
    который ждёт воркер: {"frames": [{"id": "..."}]}
    """
    frames = list_frames_for_sku(sku)
    return {"frames": [{"id": f["id"]} for f in frames]}

@router.get("/internal/frame/{frame_id}")
async def internal_frame_info(frame_id: str) -> Dict[str, Any]:
    """
    Возвращает все поля, которые нужны воркеру для обработки одного кадра.
    """
    fr = get_frame(frame_id)
        if not fr:
        raise HTTPException(status_code=404, detail="frame not found")

    # Собираем original_url из имеющегося ключа в S3
    orig_url = fr.get("original_url")
    if not orig_url:
        key = fr.get("key") or fr.get("original_key") or fr.get("s3_key")
        if not key:
            # на всякий случай: старый формат мог хранить только имя файла
            if fr.get("name") and fr.get("sku"):
                key = f"skus/{fr['sku']}/{fr['name']}"
            else:
                raise HTTPException(status_code=500, detail="frame has no S3 key")
        orig_url = s3_url(key)

    return {
        "id": fr["id"],
        "sku": fr["sku"],
        "original_url": orig_url,
        "mask_key": f"masks/{fr['sku']}/{fr['id']}.png",
        # добавляй сюда что ещё нужно воркеру (head и т.п.), если уже было раньше
    }
