from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Dict, Any, List
from ..store import (
    list_frames_for_sku, get_frame, get_sku, get_sku_by_code,
    SKU_BY_CODE, SKUS_BY_ID, SKU_FRAMES, FRAME_GENERATIONS, GENERATIONS_BY_ID
)
from .internal import _s3_public_url, _s3_signed_get, S3_REQUIRE_SIGNED, S3_BUCKET
import os

USE_DB = bool(os.environ.get("DATABASE_URL"))
if USE_DB:
    try:
        from ..database import get_session
        from .. import models
    except Exception:
        USE_DB = False

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

def _date_str(ts: float) -> str:
    return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

@router.get("/brands")
def list_brands():
    """List distinct brands (DB-aware)."""
    if USE_DB:
        from sqlalchemy import select, func
        sess = get_session()
        try:
            rows = sess.execute(select(models.SKU.brand).where(models.SKU.brand.is_not(None)).group_by(models.SKU.brand).order_by(models.SKU.brand)).scalars().all()
            return {"items": rows}
        finally:
            sess.close()
    # in-memory gather
    brands = set()
    for sku in SKUS_BY_ID.values():
        b = sku.get("brand")
        if b:
            brands.add(b)
    return {"items": sorted(brands)}

@router.get("/batches")
def list_batches(limit: int = 14):
    if USE_DB:
        from sqlalchemy import select, func
        sess = get_session()
        try:
            # aggregate frames per sku with status counts
            Frame = models.Frame; SKU = models.SKU
            from sqlalchemy import case
            done_case = case((Frame.status == models.FrameStatus.DONE, 1), else_=0)
            failed_case = case((Frame.status == models.FrameStatus.FAILED, 1), else_=0)
            rows = sess.execute(
                select(
                    SKU.id, SKU.code, SKU.brand,
                    func.date_trunc('day', SKU.created_at).label('d'),
                    func.count(Frame.id).label('frames'),
                    func.sum(done_case).label('done'),
                    func.sum(failed_case).label('failed')
                ).join(Frame, Frame.sku_id == SKU.id, isouter=True)
                .group_by(SKU.id, SKU.code, SKU.brand, 'd')
                .order_by(func.max(SKU.created_at).desc())
            ).fetchall()
            buckets: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                date = r.d.date().isoformat() if hasattr(r.d, 'date') else str(r.d)[:10]
                b = buckets.setdefault(date, {"date": date, "total": 0, "done": 0, "failed": 0, "inProgress": 0})
                b["total"] += 1
                if r.frames and r.frames == r.done:
                    b["done"] += 1
                elif r.frames and r.frames == r.failed:
                    b["failed"] += 1
                else:
                    b["inProgress"] += 1
            items = sorted(buckets.values(), key=lambda x: x["date"], reverse=True)[:limit]
            return {"items": items}
        finally:
            sess.close()
    # fallback in-memory
    batches: Dict[str, Dict[str, Any]] = {}
    for sku in SKUS_BY_ID.values():
        created = sku.get("created_at") or 0
        date = _date_str(created)
        b = batches.setdefault(date, {"date": date, "total": 0, "done": 0, "failed": 0, "inProgress": 0})
        b["total"] += 1
        frames = list_frames_for_sku(sku["id"]) or []
        if frames:
            completed = sum(1 for fr in frames if fr.get("status") in ("DONE", "completed"))
            failed = sum(1 for fr in frames if fr.get("status") in ("FAILED", "failed"))
            if completed == len(frames): b["done"] += 1
            elif failed == len(frames): b["failed"] += 1
            else: b["inProgress"] += 1
        else:
            b["inProgress"] += 1
    items = sorted(batches.values(), key=lambda x: x["date"], reverse=True)[:limit]
    return {"items": items}

@router.get("/skus")
def list_skus(date: str, brand: str | None = None):
    # return per-sku progress for given date
    if USE_DB:
        from sqlalchemy import select, func
        sess = get_session()
        try:
            Frame = models.Frame; SKU = models.SKU
            from sqlalchemy import case
            done_case = case((Frame.status == models.FrameStatus.DONE, 1), else_=0)
            failed_case = case((Frame.status == models.FrameStatus.FAILED, 1), else_=0)
            q = (
                select(
                    SKU.id, SKU.code, SKU.brand,
                    func.count(Frame.id),
                    func.sum(done_case),
                    func.sum(failed_case)
                ).join(Frame, Frame.sku_id == SKU.id, isouter=True)
                .where(func.date_trunc('day', SKU.created_at) == date)
                .group_by(SKU.id, SKU.code, SKU.brand)
                .order_by(SKU.id.desc())
            )
            if brand:
                from sqlalchemy import and_
                q = q.where(SKU.brand == brand)
            rows = sess.execute(q).fetchall()
            items: List[Dict[str, Any]] = []
            for r in rows:
                total = r[3] or 0; done = r[4] or 0; failed = r[5] or 0
                status = "IN_PROGRESS"
                if total and done == total: status = "DONE"
                elif failed and failed == total: status = "FAILED"
                items.append({
                    "id": r.id,
                    "sku": r.code,
                    "brand": r.brand,
                    "frames": total,
                    "done": done,
                    "status": status,
                    "updatedAt": datetime.utcnow().isoformat(),
                    "headProfile": None,
                })
            return {"items": items}
        finally:
            sess.close()
    out: List[Dict[str, Any]] = []
    for sku in SKUS_BY_ID.values():
        if _date_str(sku.get("created_at") or 0) != date: continue
        if brand and sku.get("brand") != brand: continue
        frames = list_frames_for_sku(sku["id"]) or []
        total = len(frames)
        done = sum(1 for fr in frames if fr.get("status") in ("DONE", "completed"))
        failed = sum(1 for fr in frames if fr.get("status") in ("FAILED", "failed"))
        status = "IN_PROGRESS"
        if total and done == total: status = "DONE"
        elif failed and failed == total: status = "FAILED"
        out.append({
            "id": sku["id"], "sku": sku.get("code"), "brand": sku.get("brand"), "frames": total, "done": done,
            "status": status, "updatedAt": datetime.utcnow().isoformat(), "headProfile": sku.get("head_id")
        })
    return {"items": out}

@router.get("/sku/{code}")
def sku_view(code: str):
    if USE_DB:
        sku = get_sku_by_code(code)
        if not sku:
            raise HTTPException(404, "sku not found")
        sid = sku["id"]
    else:
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
    brand = None
    if USE_DB and sku:
        brand = sku.get("brand")
    elif not USE_DB:
        sku_local = SKUS_BY_ID.get(sid)
        brand = sku_local.get("brand") if sku_local else None
    return {"sku": {"id": sid, "code": code, "brand": brand}, "frames": frame_views}
