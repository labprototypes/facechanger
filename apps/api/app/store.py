# apps/api/app/store.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from itertools import count
from time import time
from threading import RLock
import os

"""Unified store layer (in-memory + DB).

При наличии переменной окружения DATABASE_URL используется PostgreSQL через SQLAlchemy.
Иначе — fallback на in-memory (поведение как раньше). Это позволяет запускать
локально без БД и постепенно мигрировать код вызовов.
"""

USE_DB = bool(os.environ.get("DATABASE_URL"))
if USE_DB:
    try:
        from .database import get_session
        from . import models
    except Exception as e:  # если импорт не удался — откатываемся
        print(f"[store] disable DB mode: {e}")
        USE_DB = False

_lock = RLock()

# ---------------- In-memory (fallback) ----------------
SKU_BY_CODE: Dict[str, int] = {}
SKU_FRAMES: Dict[int, List[int]] = {}
SKUS_BY_ID: Dict[int, Dict[str, Any]] = {}
FRAMES_BY_ID: Dict[int, Dict[str, Any]] = {}
FRAMES = FRAMES_BY_ID
GENERATIONS_BY_ID: Dict[int, Dict[str, Any]] = {}
FRAME_GENERATIONS: Dict[int, List[int]] = {}
_sku_counter = count(1)
_frame_counter = count(1)
_generation_counter = count(1)
HEADS: Dict[int, Dict[str, Any]] = {}
NEXT_HEAD_ID = 1


def create_head(payload: Dict[str, Any]):
    global NEXT_HEAD_ID
    head_id = NEXT_HEAD_ID; NEXT_HEAD_ID += 1
    HEADS[head_id] = {
        "id": head_id,
        "name": payload["name"],
        "trigger": payload.get("trigger", ""),
        "model_version": payload["model_version"],
        "params": payload.get("params", {}),
    }
    return HEADS[head_id]


def _now() -> float: return time()

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
def register_sku(code: str, brand: str | None = None) -> int:
    if USE_DB:
        from sqlalchemy import select
        sess = get_session()
        try:
            sku = sess.execute(select(models.SKU).where(models.SKU.code == code)).scalar_one_or_none()
            if sku:
                return sku.id
            sku = models.SKU(code=code, brand=brand)
            sess.add(sku); sess.commit(); sess.refresh(sku)
            return sku.id
        finally:
            sess.close()
    with _lock:
        if code in SKU_BY_CODE:
            return SKU_BY_CODE[code]
        sid = next(_sku_counter)
        SKU_BY_CODE[code] = sid
        SKU_FRAMES.setdefault(sid, [])
        SKUS_BY_ID[sid] = {"id": sid, "code": code, "brand": brand, "created_at": _now()}
        return sid

def get_sku(sku_id: int) -> Optional[Dict[str, Any]]:
    if USE_DB:
        sess = get_session()
        try:
            sku = sess.get(models.SKU, int(sku_id))
            if not sku:
                return None
            return {"id": sku.id, "code": sku.code, "brand": sku.brand, "created_at": sku.created_at.timestamp() if getattr(sku.created_at,'timestamp',None) else None}
        finally:
            sess.close()
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
    if USE_DB:
        sess = get_session()
        try:
            # Optionally resolve/persist head profile id (by trigger token) if head payload present
            head_profile_id = None
            if head and (trig := head.get("trigger_token") or head.get("trigger")):
                from sqlalchemy import select
                hp = sess.execute(select(models.HeadProfile).where(models.HeadProfile.trigger_token == trig)).scalar_one_or_none()
                if hp:
                    head_profile_id = hp.id
            fr = models.Frame(sku_id=int(sku_id), original_key=original_key or "", status=models.FrameStatus.NEW)
            if head_profile_id is not None:
                # attach via sku.head_profile_id? No, Frame only links to SKU; we keep head_profile per frame via SKU relation
                # For now we do nothing extra; could denormalize later.
                pass
            sess.add(fr); sess.commit(); sess.refresh(fr)
            return fr.id
        finally:
            sess.close()
    fid = next_frame_id()
    add_frame({
        "id": fid,
        "sku": {"id": int(sku_id), "code": _code_for_sku(int(sku_id))},
        "original_key": original_key,
        "original_url": original_url,
        "head": head or {"trigger_token": "tnkfwm1", "prompt_template": "a photo of {token} female model"},
        "status": "queued",
        "created_at": _now(),
    })
    return fid

def add_frame(frame: Dict[str, Any]) -> int:
    with _lock:
        fid = int(frame["id"])
        FRAMES_BY_ID[fid] = frame
        SKU_FRAMES.setdefault(int(frame["sku"]["id"]), []).append(fid)
        FRAME_GENERATIONS.setdefault(fid, [])
    return fid

def get_frame(frame_id: int) -> Optional[Dict[str, Any]]:
    if USE_DB:
        from sqlalchemy import select
        sess = get_session()
        try:
            fr = sess.get(models.Frame, int(frame_id))
            if not fr:
                return None
            sku = sess.get(models.SKU, fr.sku_id)
            head_payload = None
            if sku and sku.head_profile_id:
                hp = sess.get(models.HeadProfile, sku.head_profile_id)
                if hp:
                    head_payload = {
                        "id": hp.id,
                        "name": hp.name,
                        "trigger_token": hp.trigger_token,
                        "model_version": hp.replicate_model,
                        "params": hp.params or {},
                    }
            versions = sess.execute(select(models.FrameOutputVersion).where(models.FrameOutputVersion.frame_id == fr.id).order_by(models.FrameOutputVersion.version_index)).scalars().all()
            outs_versions = [list(v.keys) for v in versions]
            flat: List[str] = []
            for v in outs_versions:
                flat.extend(v)
            favs = sess.execute(select(models.FrameFavorite).where(models.FrameFavorite.frame_id == fr.id)).scalars().all()
            favorites = [f.key for f in favs]
            return {
                "id": fr.id,
                "sku": {"id": sku.id if sku else fr.sku_id, "code": sku.code if sku else None},
                "original_key": fr.original_key,
                "mask_key": fr.mask_key,
                "status": fr.status.value if hasattr(fr.status,'value') else fr.status,
                "outputs": flat,
                "outputs_versions": outs_versions or None,
                "favorites": favorites,
                "pending_params": fr.pending_params,
                "head": head_payload,
            }
        finally:
            sess.close()
    return FRAMES_BY_ID.get(int(frame_id))

def list_frames() -> List[Dict[str, Any]]:
    return list(FRAMES_BY_ID.values())

def list_frames_for_sku(sku_id: int) -> List[Dict[str, Any]]:
    if USE_DB:
        from sqlalchemy import select
        sess = get_session()
        try:
            rows = sess.execute(select(models.Frame).where(models.Frame.sku_id == int(sku_id))).scalars().all()
            out = []
            for fr in rows:
                obj = get_frame(fr.id)
                if obj:
                    out.append(obj)
            return out
        finally:
            sess.close()
    sid = _normalize_sku_id(sku_id)
    ids = SKU_FRAMES.get(sid, [])
    return [FRAMES_BY_ID[i] for i in ids if i in FRAMES_BY_ID]

def set_frame_status(frame_id: int, status: str) -> None:
    if USE_DB:
        sess = get_session()
        try:
            fr = sess.get(models.Frame, int(frame_id))
            if not fr:
                return
            norm = status.upper()
            mapping = {
                "QUEUED": models.FrameStatus.QUEUED,
                "GENERATING": models.FrameStatus.RUNNING,
                "RUNNING": models.FrameStatus.RUNNING,
                "DONE": models.FrameStatus.DONE,
                "COMPLETED": models.FrameStatus.DONE,
                "FAILED": models.FrameStatus.FAILED,
                "MASKED": models.FrameStatus.MASKED,
                "NEW": models.FrameStatus.NEW,
            }
            fr.status = mapping.get(norm, fr.status)
            sess.add(fr); sess.commit(); return
        finally:
            sess.close()
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
    if USE_DB:
        from sqlalchemy import select, func
        sess = get_session()
        try:
            fr = sess.get(models.Frame, int(frame_id))
            if not fr:
                return
            count_versions = sess.execute(select(func.count(models.FrameOutputVersion.id)).where(models.FrameOutputVersion.frame_id == fr.id)).scalar() or 0
            ver = models.FrameOutputVersion(frame_id=fr.id, version_index=count_versions + 1, keys=list(outputs))
            sess.add(ver)
            if fr.status not in (models.FrameStatus.FAILED, models.FrameStatus.DONE):
                fr.status = models.FrameStatus.DONE
                sess.add(fr)
            sess.commit(); return
        finally:
            sess.close()
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is None:
            return
        vers = fr.setdefault("outputs_versions", [])
        if not vers and fr.get("outputs"):
            vers.append(list(fr["outputs"]))
        vers.append(list(outputs))
        flat: List[str] = []
        for v in vers:
            flat.extend(v)
        fr["outputs"] = flat
        fr["updated_at"] = _now()

def set_frame_mask(frame_id: int, mask_key: str) -> None:
    if USE_DB:
        sess = get_session()
        try:
            fr = sess.get(models.Frame, int(frame_id))
            if not fr:
                return
            fr.mask_key = mask_key
            sess.add(fr); sess.commit(); return
        finally:
            sess.close()
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is not None:
            fr["mask_key"] = mask_key
            fr["updated_at"] = _now()

def set_frame_pending_params(frame_id: int, params: Dict[str, Any]) -> None:
    if USE_DB:
        sess = get_session()
        try:
            fr = sess.get(models.Frame, int(frame_id))
            if not fr:
                return
            merged = fr.pending_params or {}
            merged.update(params)
            fr.pending_params = merged
            sess.add(fr); sess.commit(); return
        finally:
            sess.close()
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is not None:
            fr.setdefault("pending_params", {}).update(params)
            fr["updated_at"] = _now()

def set_frame_favorites(frame_id: int, keys: List[str]) -> None:
    clean: List[str] = []
    seen = set()
    for k in keys:
        if not k or k in seen:
            continue
        seen.add(k); clean.append(k)
    if USE_DB:
        from sqlalchemy import delete as sqldelete, select
        sess = get_session()
        try:
            fr = sess.get(models.Frame, int(frame_id))
            if not fr:
                return
            sess.execute(sqldelete(models.FrameFavorite).where(models.FrameFavorite.frame_id == fr.id))
            for k in clean:
                sess.add(models.FrameFavorite(frame_id=fr.id, key=k))
            sess.commit(); return
        finally:
            sess.close()
    with _lock:
        fr = FRAMES_BY_ID.get(int(frame_id))
        if fr is not None:
            fr["favorites"] = clean
            fr["updated_at"] = _now()

def get_frame_favorites(frame_id: int) -> List[str]:
    if USE_DB:
        from sqlalchemy import select
        sess = get_session()
        try:
            favs = sess.execute(select(models.FrameFavorite).where(models.FrameFavorite.frame_id == int(frame_id))).scalars().all()
            return [f.key for f in favs]
        finally:
            sess.close()
    fr = FRAMES_BY_ID.get(int(frame_id))
    if not fr:
        return []
    return list(fr.get("favorites") or [])
def delete_frame(frame_id: int) -> None:
    if USE_DB:
        from sqlalchemy import delete as sqldelete
        sess = get_session()
        try:
            fr = sess.get(models.Frame, int(frame_id))
            if not fr:
                return
            sess.execute(sqldelete(models.FrameFavorite).where(models.FrameFavorite.frame_id == fr.id))
            sess.execute(sqldelete(models.FrameOutputVersion).where(models.FrameOutputVersion.frame_id == fr.id))
            sess.execute(sqldelete(models.Generation).where(models.Generation.frame_id == fr.id))
            sess.delete(fr); sess.commit(); return
        finally:
            sess.close()
    fid = int(frame_id)
    fr = FRAMES_BY_ID.pop(fid, None)
    if not fr:
        return
    sku = fr.get("sku") or {}
    sid = sku.get("id")
    if sid in SKU_FRAMES:
        SKU_FRAMES[sid] = [x for x in SKU_FRAMES[sid] if x != fid]
    gen_ids = FRAME_GENERATIONS.pop(fid, [])
    for gid in gen_ids:
        GENERATIONS_BY_ID.pop(gid, None)

def delete_sku(code_or_id) -> None:
    if USE_DB:
        from sqlalchemy import select, delete as sqldelete
        sess = get_session()
        try:
            sid: Optional[int] = None
            if isinstance(code_or_id, int):
                sid = code_or_id
            else:
                sku = sess.execute(select(models.SKU).where(models.SKU.code == str(code_or_id))).scalar_one_or_none()
                if sku:
                    sid = sku.id
                else:
                    try:
                        sid = int(str(code_or_id))
                    except ValueError:
                        return
            if sid is None:
                return
            frame_ids = [r.id for r in sess.execute(select(models.Frame.id).where(models.Frame.sku_id == sid)).scalars().all()]
            for fid in frame_ids:
                sess.execute(sqldelete(models.FrameFavorite).where(models.FrameFavorite.frame_id == fid))
                sess.execute(sqldelete(models.FrameOutputVersion).where(models.FrameOutputVersion.frame_id == fid))
                sess.execute(sqldelete(models.Generation).where(models.Generation.frame_id == fid))
            sess.execute(sqldelete(models.Frame).where(models.Frame.sku_id == sid))
            sess.execute(sqldelete(models.SKU).where(models.SKU.id == sid))
            sess.commit(); return
        finally:
            sess.close()
    sid = None
    if isinstance(code_or_id, int):
        sid = code_or_id
    else:
        if code_or_id in SKU_BY_CODE:
            sid = SKU_BY_CODE[code_or_id]
        else:
            try:
                sid = int(str(code_or_id))
            except ValueError:
                return
    if sid is None:
        return
    code_to_del = None
    for c, _sid in list(SKU_BY_CODE.items()):
        if _sid == sid:
            code_to_del = c; break
    if code_to_del:
        SKU_BY_CODE.pop(code_to_del, None)
    frame_ids = SKU_FRAMES.pop(sid, [])
    for fid in frame_ids:
        delete_frame(fid)
    SKUS_BY_ID.pop(sid, None)

# backward name used earlier
mark_frame_status = set_frame_status

# ---------------- Generation helpers ----------------
def register_generation(frame_id: int) -> int:
    if USE_DB:
        sess = get_session()
        try:
            gen = models.Generation(frame_id=int(frame_id))
            sess.add(gen); sess.commit(); sess.refresh(gen)
            return gen.id
        finally:
            sess.close()
    gid = next_generation_id()
    with _lock:
        GENERATIONS_BY_ID[gid] = {"id": gid, "frame_id": int(frame_id), "created_at": _now(), "prediction_id": None, "status": "created", "outputs": [], "meta": {}}
        FRAME_GENERATIONS.setdefault(int(frame_id), []).append(gid)
    return gid

def save_generation_registration(frame_id: int) -> Dict[str, Any]:
    """
    Convenience wrapper used by internal routes to register and return as JSON.
    """
    gid = register_generation(frame_id)
    return {"id": gid}

def save_generation_prediction(generation_id: int, prediction_id: str) -> None:
    if USE_DB:
        sess = get_session()
        try:
            gen = sess.get(models.Generation, int(generation_id))
            if not gen:
                return
            gen.replicate_prediction_id = prediction_id
            gen.status = models.GenStatus.RUNNING
            sess.add(gen); sess.commit(); return
        finally:
            sess.close()
    with _lock:
        gen = GENERATIONS_BY_ID.setdefault(int(generation_id), {"id": int(generation_id)})
        gen["prediction_id"] = prediction_id
        gen["updated_at"] = _now()
        gen["status"] = "submitted"

def set_generation_outputs(generation_id: int, outputs: List[str]) -> None:
    if USE_DB:
        sess = get_session()
        try:
            gen = sess.get(models.Generation, int(generation_id))
            if not gen:
                return
            gen.output_keys = list(outputs)
            gen.status = models.GenStatus.COMPLETED
            sess.add(gen); sess.commit(); return
        finally:
            sess.close()
    with _lock:
        gen = GENERATIONS_BY_ID.get(int(generation_id))
        if gen is not None:
            gen["outputs"] = outputs
            gen["updated_at"] = _now()
            gen["status"] = "completed"

def get_generation(generation_id: int) -> Optional[Dict[str, Any]]:
    if USE_DB:
        sess = get_session()
        try:
            gen = sess.get(models.Generation, int(generation_id))
            if not gen:
                return None
            return {"id": gen.id, "frame_id": gen.frame_id, "prediction_id": gen.replicate_prediction_id, "status": gen.status.value if hasattr(gen.status,'value') else gen.status, "outputs": gen.output_keys or []}
        finally:
            sess.close()
    return GENERATIONS_BY_ID.get(int(generation_id))

def generations_for_frame(frame_id: int) -> List[Dict[str, Any]]:
    if USE_DB:
        from sqlalchemy import select
        sess = get_session()
        try:
            gens = sess.execute(select(models.Generation).where(models.Generation.frame_id == int(frame_id))).scalars().all()
            return [{"id": g.id, "frame_id": g.frame_id, "prediction_id": g.replicate_prediction_id, "status": g.status.value if hasattr(g.status,'value') else g.status, "outputs": g.output_keys or []} for g in gens]
        finally:
            sess.close()
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
    for code, sid in SKU_BY_CODE.items():
        if sid == int(sku_id):
            return code
    return None

__all__ = [
    "SKU_BY_CODE", "SKU_FRAMES", "SKUS_BY_ID",
    "FRAMES_BY_ID", "FRAMES",
    "next_sku_id", "next_frame_id", "next_generation_id",
    "register_sku", "get_sku", "upsert_sku",
    "get_sku_by_code",
    "get_all_sku_codes", "list_sku_codes_by_date",
    "add_frame", "register_frame", "get_frame",
    "list_frames", "list_frames_for_sku",
    "set_frame_status", "mark_frame_status",
    "GENERATIONS_BY_ID", "FRAME_GENERATIONS",
    "register_generation", "save_generation_registration",
    "save_generation_prediction", "set_generation_outputs",
    "get_generation", "generations_for_frame",
    "set_frame_favorites", "get_frame_favorites",
    "delete_frame", "delete_sku",
]

def get_sku_by_code(code: str) -> Optional[Dict[str, Any]]:
    """Return SKU dict by code (DB-aware)."""
    if USE_DB:
        from sqlalchemy import select
        sess = get_session()
        try:
            sku = sess.execute(select(models.SKU).where(models.SKU.code == code)).scalar_one_or_none()
            if not sku:
                return None
            return {"id": sku.id, "code": sku.code, "brand": sku.brand, "created_at": sku.created_at.timestamp() if getattr(sku.created_at,'timestamp',None) else None}
        finally:
            sess.close()
    sid = SKU_BY_CODE.get(code)
    if not sid:
        return None
    return get_sku(sid)

def get_all_sku_codes() -> List[str]:
    """Возвращает список всех SKU code (DB-aware)."""
    if USE_DB:
        from sqlalchemy import select
        sess = get_session()
        try:
            rows = sess.execute(select(models.SKU.code)).scalars().all()
            return list(rows)
        finally:
            sess.close()
    return list(SKU_BY_CODE.keys())

def list_sku_codes_by_date(date: str) -> List[str]:
    """Список SKU codes по UTC дате (YYYY-MM-DD)."""
    if USE_DB:
        from sqlalchemy import select, func
        sess = get_session()
        try:
            rows = sess.execute(
                select(models.SKU.code)
                .where(func.to_char(models.SKU.created_at, 'YYYY-MM-DD') == date)
            ).scalars().all()
            return list(rows)
        finally:
            sess.close()
    # fallback: фильтруем по created_at из in-memory
    out = []
    for code, sid in SKU_BY_CODE.items():
        sku = SKUS_BY_ID.get(sid)
        if not sku:
            continue
        ts = sku.get("created_at") or 0
        import datetime
        if datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d') == date:
            out.append(code)
    return out
