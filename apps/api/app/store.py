# apps/api/app/store.py
from typing import Dict, List, Optional

# очень простой in-memory «псевдо-DB».
# В реале мы сохраняем кадры сюда в момент загрузки (ручки upload-urls/upload).
_FRAMES: Dict[str, Dict] = {}          # frame_id -> frame dict
_BY_SKU: Dict[str, List[str]] = {}      # sku -> [frame_id, ...]

def add_frame(frame: Dict) -> None:
    """
    Используется ручкой загрузки: кладём кадр в хранилище.
    Обязательные поля: id, sku, original_url
    """
    fid = frame["id"]
    _FRAMES[fid] = frame
    _BY_SKU.setdefault(frame["sku"], []).append(fid)

def list_frames_for_sku(sku: str) -> List[Dict]:
    ids = _BY_SKU.get(sku, [])
    return [ _FRAMES[i] for i in ids ]

def get_frame(frame_id: str) -> Optional[Dict]:
    return _FRAMES.get(frame_id)
