# apps/api/app/routes/internal.py
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional

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

    # ожидаемый воркером shape
    return {
        "id": fr["id"],
        "sku": {"code": fr["sku"]},
        # «голова»: по умолчанию токен Маши tnkfwm1 + дефолтный промпт
        "head": {
            "trigger_token": fr.get("head_token", "tnkfwm1"),
            "prompt_template": fr.get("prompt_template", "a photo of {token} female model"),
        },
        "original_url": fr["original_url"],
        # если маску заранее сохранили — отдаём, иначе None
        "mask_url": fr.get("mask_url"),
        # любые доп. параметры (опционально)
        "params": fr.get("params", {}),
    }
