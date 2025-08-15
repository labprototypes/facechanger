# apps/api/app/store.py
from __future__ import annotations
from typing import Any, Dict, List
from time import time
from threading import RLock

_lock = RLock()

# --- In-memory storage (временное) ---
SKU_BY_CODE: Dict[str, Dict[str, Any]] = {}
FRAMES_BY_ID: Dict[str, Dict[str, Any]] = {}   # имя, которое импортируют роуты
FRAME_BY_ID = FRAMES_BY_ID                      # алиас на всякий

def upsert_sku(code: str) -> Dict[str, Any]:
    """Создать SKU, если нет, и вернуть запись."""
    with _lock:
        sku = SKU_BY_CODE.get(code)
        if sku is None:
            sku = {"code": code, "created_at": time()}
            SKU_BY_CODE[code] = sku
        return sku

def add_frame(data: Dict[str, Any]) -> Dict[str, Any]:
    """Сохранить/обновить кадр."""
    frame = {
        "id": data["id"],
        "sku": data.get("sku") if isinstance(data.get("sku"), str) else data.get("sku", ""),
        "original_url": data["original_url"],
        "head_token": data.get("head_token", "tnkfwm1"),
        "prompt_template": data.get("prompt_template", "a photo of {token} female model"),
        "params": data.get("params", {}),
        "status": data.get("status", "QUEUED"),
        "created_at": time(),
    }
    with _lock:
        FRAMES_BY_ID[frame["id"]] = frame
    # гарантируем наличие SKU
    if frame["sku"]:
        upsert_sku(frame["sku"])
    return frame

def get_frame(frame_id: str) -> Dict[str, Any] | None:
    return FRAMES_BY_ID.get(frame_id)

def list_frames(sku_code: str) -> List[Dict[str, Any]]:
    return [f for f in FRAMES_BY_ID.values() if f.get("sku") == sku_code]

__all__ = [
    "SKU_BY_CODE",
    "FRAMES_BY_ID",
    "FRAME_BY_ID",
    "upsert_sku",
    "add_frame",
    "get_frame",
    "list_frames",
]
