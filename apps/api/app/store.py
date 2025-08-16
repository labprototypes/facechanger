# apps/api/app/store.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from itertools import count
from time import time
from threading import RLock

# ---------------- In-memory store (временное) ----------------
_lock = RLock()

# SKU и кадры
SKU_BY_CODE: Dict[str, Dict[str, Any]] = {}           # code -> sku
SKUS_BY_ID: Dict[str, Dict[str, Any]] = {}            # id -> sku
FRAMES_BY_ID: Dict[str, Dict[str, Any]] = {}          # id -> frame
FRAME_BY_ID = FRAMES_BY_ID                             # алиас на всякий
FRAMES = FRAMES_BY_ID  # старое имя, которое ждут роуты

# Счётчики для id (на время разработки)
_sku_counter = count(1)
_frame_counter = count(1)

def next_sku_id() -> str:
    """Вернёт новый id для SKU (временная реализация)."""
    return f"sku_{next(_sku_counter)}"

def next_frame_id() -> str:
    """Вернёт новый id для кадра (временная реализация)."""
    return f"fr_{next(_frame_counter)}"

# ---------------- SKU helpers ----------------
def get_sku(code: str) -> Optional[Dict[str, Any]]:
    return SKU_BY_CODE.get(code)

def upsert_sku(code: str) -> Dict[str, Any]:
    """Создать SKU, если его нет, и вернуть запись."""
    with _lock:
        sku = SKU_BY_CODE.get(code)
        if sku is None:
            sku = {
                "id": next_sku_id(),
                "code": code,
                "created_at": time(),
            }
            SKU_BY_CODE[code] = sku
            SKUS_BY_ID[sku["id"]] = sku
        return sku

def register_sku(code: str) -> Dict[str, Any]:
    """Синоним upsert_sku (некоторые места могут импортировать другое имя)."""
    return upsert_sku(code)

# ---------------- Frames helpers ----------------
def add_frame(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Сохранить/обновить кадр. Ожидаемые поля:
      id, sku (код), original_url, mask_url?, head_token?, prompt_template?, params?, status?
    """
    frame_id = data.get("id") or next_frame_id()
    frame = {
        "id": frame_id,
        "sku": data.get("sku", ""),
        "original_url": data.get("original_url"),
        "mask_url": data.get("mask_url"),
        "head_token": data.get("head_token", "tnkfwm1"),
        "prompt_template": data.get("prompt_template", "a photo of {token} female model"),
        "params": data.get("params", {}),
        "status": data.get("status", "QUEUED"),
        "created_at": time(),
        "updated_at": time(),
    }
    with _lock:
        FRAMES_BY_ID[frame_id] = frame
    # гарантируем наличие SKU
    if frame["sku"]:
        upsert_sku(frame["sku"])
    return frame

def register_frame(
    sku_code: str,
    *,
    original_url: str,
    mask_url: Optional[str] = None,
    head_token: str = "tnkfwm1",
    prompt_template: str = "a photo of {token} female model",
    params: Optional[Dict[str, Any]] = None,
    status: str = "QUEUED",
) -> Dict[str, Any]:
    """Удобный конструктор кадра."""
    return add_frame({
        "id": next_frame_id(),
        "sku": sku_code,
        "original_url": original_url,
        "mask_url": mask_url,
        "head_token": head_token,
        "prompt_template": prompt_template,
        "params": params or {},
        "status": status,
    })

def get_frame(frame_id: str) -> Optional[Dict[str, Any]]:
    return FRAMES_BY_ID.get(frame_id)

def list_frames(sku_code: str) -> List[Dict[str, Any]]:
    return [f for f in FRAMES_BY_ID.values() if f.get("sku") == sku_code]

def set_frame_status(frame_id: str, status: str, **extra: Any) -> Optional[Dict[str, Any]]:
    with _lock:
        fr = FRAMES_BY_ID.get(frame_id)
        if not fr:
            return None
        fr["status"] = status
        fr.update(extra)
        fr["updated_at"] = time()
        return fr

# Часто используемые алиасы — чтобы любые импорты не падали
mark_frame_status = set_frame_status

__all__ = [
    # сторы
    "SKU_BY_CODE", "SKUS_BY_ID", "FRAMES_BY_ID", "FRAME_BY_ID", "FRAMES",
    # генераторы id
    "next_sku_id", "next_frame_id",
    # SKU API
    "get_sku", "upsert_sku", "register_sku",
    # Frames API
    "add_frame", "register_frame", "get_frame", "list_frames",
    "set_frame_status", "mark_frame_status",
]
