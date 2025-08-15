import uuid
from fastapi import APIRouter
from ..store import FRAMES, SKU_FRAMES, GENERATIONS

router = APIRouter(tags=["internal"])

@router.get("/internal/sku/{sku_id}/frames")
async def list_frames_for_sku(sku_id: int):
    ids = SKU_FRAMES.get(sku_id, [])
    return {"frames": [FRAMES[i] for i in ids]}

@router.get("/internal/frame/{frame_id}")
async def get_frame(frame_id: int):
    return FRAMES[frame_id]

@router.post("/internal/frame/{frame_id}/generation")
async def create_generation(frame_id: int):
    gen_id = str(uuid.uuid4())
    GENERATIONS[gen_id] = {"frame_id": frame_id}
    return {"id": gen_id}

@router.post("/internal/generation/{gen_id}/prediction")
async def attach_prediction(gen_id: str, payload: dict):
    GENERATIONS.setdefault(gen_id, {}).update(payload)
    return {"ok": True}
