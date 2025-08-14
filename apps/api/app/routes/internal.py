import uuid
from fastapi import APIRouter

router = APIRouter(tags=["internal"])

# Простейшие in-memory заглушки (чтоб воркеру было что дергать)
# frame -> минимальный набор, который воркер ждёт
_FRAMES = {
    1: {
        "id": 1,
        "sku": {"code": "SKU-DEMO"},
        # любой общедоступный URL для теста; заменим на S3 позже
        "original_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/59/Empty.png/640px-Empty.png",
        "head": {
            "trigger_token": "tnkfwm1",
            "prompt_template": "a photo of {token} female model",
        },
    }
}
_SKU_FRAMES = {100: [1]}
_GENERATIONS = {}

@router.get("/internal/sku/{sku_id}/frames")
async def list_frames_for_sku(sku_id: int):
    ids = _SKU_FRAMES.get(sku_id, [])
    return {"frames": [_FRAMES[i] for i in ids]}

@router.get("/internal/frame/{frame_id}")
async def get_frame(frame_id: int):
    return _FRAMES[frame_id]

@router.post("/internal/frame/{frame_id}/generation")
async def create_generation(frame_id: int):
    gen_id = str(uuid.uuid4())
    _GENERATIONS[gen_id] = {"frame_id": frame_id}
    return {"id": gen_id}

@router.post("/internal/generation/{gen_id}/prediction")
async def attach_prediction(gen_id: str, payload: dict):
    _GENERATIONS.setdefault(gen_id, {}).update(payload)
    return {"ok": True}
