from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import joinedload
from ..database import db_session
from ..models import SKU, Frame, FrameStatus, Generation, GenStatus
from ..s3util import public_url

router = APIRouter(prefix="/internal")

@router.get("/sku/{sku_id}/frames")
def sku_frames(sku_id: int):
    db = db_session()
    sku = db.query(SKU).options(joinedload(SKU.frames)).filter(SKU.id == sku_id).first()
    if not sku: raise HTTPException(404, "not found")
    return {"frames": [{"id": f.id} for f in sku.frames]}

@router.get("/frame/{frame_id}")
def frame_info(frame_id: int):
    db = db_session()
    fr = db.query(Frame).join(SKU).options(joinedload(Frame.sku), joinedload(SKU.head)).filter(Frame.id == frame_id).first()
    if not fr: raise HTTPException(404, "not found")
    return {
        "id": fr.id,
        "sku": {"id": fr.sku.id, "code": fr.sku.code},
        "head": fr.sku.head and {
            "id": fr.sku.head.id,
            "trigger_token": fr.sku.head.trigger_token,
            "prompt_template": fr.sku.head.prompt_template,
        },
        "original_url": public_url(fr.original_key),
    }

@router.post("/frame/{frame_id}/generation")
def create_generation(frame_id: int):
    db = db_session()
    fr = db.query(Frame).filter(Frame.id == frame_id).first()
    if not fr: raise HTTPException(404, "frame not found")
    fr.status = FrameStatus.RUNNING
    gen = Generation(frame_id=frame_id, status=GenStatus.RUNNING)
    db.add(gen); db.commit(); db.refresh(gen)
    return {"id": gen.id}

@router.post("/generation/{gen_id}/prediction")
def set_prediction(gen_id: int, payload: dict):
    db = db_session()
    gen = db.query(Generation).filter(Generation.id == gen_id).first()
    if not gen: raise HTTPException(404, "generation not found")
    gen.replicate_prediction_id = payload.get("prediction_id")
    db.commit()
    return {"ok": True}
