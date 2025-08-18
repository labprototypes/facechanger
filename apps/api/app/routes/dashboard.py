from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict, Any, List
from ..store import SKUS_BY_ID, SKU_FRAMES, FRAMES_BY_ID, FRAME_GENERATIONS, GENERATIONS_BY_ID, list_frames_for_sku, SKU_BY_CODE
from .internal import _s3_public_url, _s3_signed_get, S3_REQUIRE_SIGNED, S3_BUCKET

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

def _date_str(ts: float) -> str:
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

@router.get("/batches")
def list_batches(limit: int = 14):
    # derive batches by sku created date
    batches: Dict[str, Dict[str, Any]] = {}
    for sku in SKUS_BY_ID.values():
        created = sku.get("created_at") or 0
        date = _date_str(created)
        b = batches.setdefault(date, {"date": date, "total": 0, "done": 0, "failed": 0, "inProgress": 0})
        b["total"] += 1
        # naive progress: if all frames completed -> done
        frames = list_frames_for_sku(sku["id"]) or []
        if frames:
            completed = sum(1 for fr in frames if fr.get("status") in ("DONE", "completed"))
            failed = sum(1 for fr in frames if fr.get("status") in ("FAILED", "failed"))
            if completed == len(frames):
                b["done"] += 1
            elif failed == len(frames):
                b["failed"] += 1
            else:
                b["inProgress"] += 1
        else:
            b["inProgress"] += 1
    # sort by date desc
    items = sorted(batches.values(), key=lambda x: x["date"], reverse=True)[:limit]
    return {"items": items}

@router.get("/skus")
def list_skus(date: str):
    # return per-sku progress for given date
    out: List[Dict[str, Any]] = []
    for sku in SKUS_BY_ID.values():
        if _date_str(sku.get("created_at") or 0) != date:
            continue
        frames = list_frames_for_sku(sku["id"]) or []
        total = len(frames)
        done = sum(1 for fr in frames if fr.get("status") in ("DONE", "completed"))
        failed = sum(1 for fr in frames if fr.get("status") in ("FAILED", "failed"))
        status = "IN_PROGRESS"
        if total and done == total:
            status = "DONE"
        elif failed and failed == total:
            status = "FAILED"
        out.append({
            "id": sku["id"],
            "sku": sku.get("code"),
            "frames": total,
            "done": done,
            "status": status,
            "updatedAt": datetime.utcnow().isoformat(),
            "headProfile": sku.get("head_id"),
        })
    return {"items": out}

@router.get("/sku/{code}")
def sku_view(code: str):
    if code not in SKU_BY_CODE:
        raise HTTPException(404, "sku not found")
    sid = SKU_BY_CODE[code]
    frames = list_frames_for_sku(sid) or []
    frame_views: List[Dict[str, Any]] = []
    for fr in frames:
        gens_ids = FRAME_GENERATIONS.get(fr["id"], [])
        gens = [GENERATIONS_BY_ID.get(g) for g in gens_ids if g in GENERATIONS_BY_ID]
        mask_key = fr.get("mask_key")
        mask_url = None
        if mask_key:
            try:
                mask_url = _s3_signed_get(mask_key) if S3_REQUIRE_SIGNED else _s3_public_url(mask_key)
            except Exception:
                pass
        frame_views.append({
            "id": fr["id"],
            "status": fr.get("status"),
            "original_key": fr.get("original_key"),
            "mask_key": mask_key,
            "mask_url": mask_url,
            "generations": gens,
        })
    return {"sku": {"id": sid, "code": code}, "frames": frame_views}
