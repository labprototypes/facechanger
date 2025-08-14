from fastapi import APIRouter

router = APIRouter(prefix="/heads", tags=["heads"])

# Заглушечный список голов (профилей). "Маша" = tnkfwm1
HEADS = [
    {
        "id": 1,
        "name": "Маша",
        "model": "labprototypes/tnkfwm2",
        "trigger_token": "tnkfwm1",
        "prompt_template": "a photo of {token} female model",
    }
]

@router.get("")
async def list_heads():
    return {"items": HEADS}

@router.get("/{head_id}")
async def get_head(head_id: int):
    for h in HEADS:
        if h["id"] == head_id:
            return h
    return {"detail": "not found"}
