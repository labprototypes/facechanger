# apps/api/app/store.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from itertools import count
from time import time
from threading import RLock

# ---------------- In-memory store (temporary) ----------------
_lock = RLock()

# SKU and Frames registries
SKU_BY_CODE: Dict[str, int] = {}            # "HEFQ" -> 1
SKU_FRAMES: Dict[int, List[int]] = {}       # 1 -> [1,2,3]
SKUS_BY_ID: Dict[int, Dict[str, Any]] = {}  # 1 -> {id, code, created_at}
FRAMES_BY_ID: Dict[int, Dict[str, Any]] = {}  # 1 -> frame record
FRAMES = FRAMES_BY_ID                        # alias for older imports

# Generations registry (optional but useful for /internal endpoints)
GENERATIONS_BY_ID: Dict[int, Dict[str, Any]] = {}   # 1 -> {id, frame_id, ...}
FRAME_GENERATIONS: Dict[int, List[int]] = {}        # frame_id -> [gen_ids]

# Auto-increment counters
_sku_counter = count(1)
_frame_counter = count(1)
_generation_counter = count(1)

HEADS = {}              # head_id -> {id, name, trigger, model_version, params}
NEXT_HEAD_ID = 1

def create_head(payload):
    global NEXT_HEAD_ID
    head_id = NEXT_HEAD_ID
    NEXT_HEAD_ID += 1
    HEADS[head_id] = {
        "id": head_id,
        "name": payload["name"],
        "trigger": payload.get("trigger", ""),
        "model_version": payload["model_version"],  # owner/model:version_sha
        "params": payload.get("params", {}),        # dict дефолтов: steps, guidance, prompt_strength и т.п.
    }
    return HEADS[head_id]

def _now() -> float:
    return time()

# ---------------- ID helpers ----------------
def next_sku_id() -> int:
    """Return next integer SKU id."""
    with _lock:
        return next(_sku_counter)

def next_frame_id() -> int:
    """Return next integer Frame id."""
    with _lock:
        return next(_frame_counter)

def next_generation_id() -> int:
    """Return next integer Generation id."""
    with _lock:
        return next(_generation_counter)

# ---------------- SKU helpers ----------------
def register_sku(code: str) -> int:
    """
    Ensure SKU exists for given code; return its integer id.
    """
    with _lock:
        if code in SKU_BY_CODE:
            sid = SKU_BY_CODE[code]
        else:
            sid = next(_sku_counter)
            SKU_BY_CODE[code] = sid
            SKU_FRAMES.setdefault(sid, [])
            SKUS_BY_ID[sid] = {
                "id": sid,
                "code": code,
                "created_at": _now(),
            }
    return sid

def get_sku(sku_id: int) -> Optional[Dict[str, Any]]:
    return SKUS_BY_ID.get(int(sku_id))

def upsert_sku(sku_id: int, data: Dict[str, Any]) -> None:
    with _lock:
        rec = SKUS_BY_ID.setdefault(int(sku_id), {"id": int(sku_id), "created_at": _now()})
        rec.update(data)

# ---------------- Frame helpers ----------------
def register_frame(
    sku_id: int,
    original_key: Optional[str] = None,
    original_url: Optional[str] = None,
    head: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Create a new frame record and attach to the SKU.
    """
    fid = next_frame_id()
    add_frame(
        {
            "id": fid,
            "sku": {"id": int(sku_id), "code": _code_for_sku(int(sku_id))},
            "original_key": original_key,
            "original_url": original_url,
            "head": head or {
                "trigger_token": "tnkfwm1",
                "prompt_template": "a photo of {token} female model",
            },
            "status": "queued",
            "created_at": _now(),
        }
    )
    return fid

def add_frame(frame: Dict[str, Any]) -> int:
    with _lock:
        fid = int(frame["id"])
        FRAMES_BY_ID[fid] = frame
        SKU_FRAMES.setdefault(int(frame["sku"]["id"]), []).append(fid)
        FRAME_GENERATIONS.setdefault(fid, [])
    return fid

def get_frame(frame_id: int) -> Optional[Dict[str, Any]]:
    return FRAMES_BY_ID.get(int(frame_id))

def list_frames() -> List[Dict[str, Any]]:
    return list(FRAMES_BY_ID.values())

def list_frames_for_sku(sku_id: int) -> List[Dict[str, Any]]:
    """
    Return list of frame records for SKU. Accepts both int and str id like 'sku_1'.
    """
    sid = _normalize_sku_id(sku_id)
    ids = SKU_FRAMES.get(sid, [])
    return [FRAMES_BY_ID[i] for i in ids if i in FRAMES_BY_ID]

def set_frame_status(frame_id: int, status: str) -> None:
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is not None:
            fr["status"] = status
            fr["updated_at"] = _now()

def set_frame_outputs(frame_id: int, outputs: List[str]) -> None:
    """Attach outputs (list of S3 keys) to a frame record.
    This lets UI endpoints that only look at frame objects expose generation results
    without separately traversing GENERATIONS state.
    """
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is not None:
            fr["outputs"] = list(outputs)
            fr["updated_at"] = _now()

def append_frame_outputs_version(frame_id: int, outputs: List[str]) -> None:
    """Append a new outputs version (list of keys) keeping prior generations.
    Maintains flattened fr['outputs'] for backward compatibility and a
    structured fr['outputs_versions'] = [ [keys_v1], [keys_v2], ... ]."""
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is None:
            return
        vers = fr.setdefault("outputs_versions", [])
        # if fr already has outputs but no versions, seed versions with that list
        if not vers and fr.get("outputs"):
            vers.append(list(fr["outputs"]))
        vers.append(list(outputs))
        # rebuild flattened outputs (latest aggregate)
        flat: List[str] = []
        for v in vers:
            flat.extend(v)
        fr["outputs"] = flat
        fr["updated_at"] = _now()

def set_frame_mask(frame_id: int, mask_key: str) -> None:
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is not None:
            fr["mask_key"] = mask_key
            fr["updated_at"] = _now()

def set_frame_pending_params(frame_id: int, params: Dict[str, Any]) -> None:
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is not None:
            fr.setdefault("pending_params", {}).update(params)
            fr["updated_at"] = _now()

# backward name used earlier
mark_frame_status = set_frame_status

# ---------------- Generation helpers ----------------
def register_generation(frame_id: int) -> int:
    gid = next_generation_id()
    with _lock:
        GENERATIONS_BY_ID[gid] = {
            "id": gid,
            "frame_id": int(frame_id),
            "created_at": _now(),
            "prediction_id": None,
            "status": "created",
            "outputs": [],
            "meta": {},
        }
        FRAME_GENERATIONS.setdefault(int(frame_id), []).append(gid)
    return gid

def save_generation_registration(frame_id: int) -> Dict[str, Any]:
    """
    Convenience wrapper used by internal routes to register and return as JSON.
    """
    gid = register_generation(frame_id)
    return {"id": gid}

def save_generation_prediction(generation_id: int, prediction_id: str) -> None:
    with _lock:
        gen = GENERATIONS_BY_ID.setdefault(int(generation_id), {"id": int(generation_id)})
        gen["prediction_id"] = prediction_id
        gen["updated_at"] = _now()
        gen["status"] = "submitted"

def set_generation_outputs(generation_id: int, outputs: List[str]) -> None:
    with _lock:
        gen = GENERATIONS_BY_ID.get(int(generation_id))
        if gen is not None:
            gen["outputs"] = outputs
            gen["updated_at"] = _now()
            gen["status"] = "completed"

def get_generation(generation_id: int) -> Optional[Dict[str, Any]]:
    return GENERATIONS_BY_ID.get(int(generation_id))

def generations_for_frame(frame_id: int) -> List[Dict[str, Any]]:
    gids = FRAME_GENERATIONS.get(int(frame_id), [])
    return [GENERATIONS_BY_ID[g] for g in gids if g in GENERATIONS_BY_ID]

# ---------------- Utilities ----------------
def _normalize_sku_id(sku_id_like) -> int:
    """
    Accept 1 or '1' or 'sku_1' and return 1.
    """
    if isinstance(sku_id_like, int):
        return sku_id_like
    s = str(sku_id_like)
    if s.startswith("sku_"):
        s = s.split("_", 1)[1]
    try:
        return int(s)
    except ValueError:
        # unknown -> create new SKU id to avoid crashes (but better to fix caller)
        return register_sku(str(sku_id_like))

def _code_for_sku(sku_id: int) -> Optional[str]:
    # reverse lookup
    for code, sid in SKU_BY_CODE.items():
        if sid == int(sku_id):
            return code
    return None

__all__ = [
    # stores
    "SKU_BY_CODE", "SKU_FRAMES", "SKUS_BY_ID",
    "FRAMES_BY_ID", "FRAMES",
    # id generators
    "next_sku_id", "next_frame_id", "next_generation_id",
    # SKU API
    "register_sku", "get_sku", "upsert_sku",
    # Frame API
    "add_frame", "register_frame", "get_frame",
    "list_frames", "list_frames_for_sku",
    "set_frame_status", "mark_frame_status",
    # Generation API
    "GENERATIONS_BY_ID", "FRAME_GENERATIONS",
    "register_generation", "save_generation_registration",
    "save_generation_prediction", "set_generation_outputs",
    "get_generation", "generations_for_frame",
]
