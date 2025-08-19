from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/webhooks/replicate")
async def replicate_webhook_public(payload: dict, request: Request):
    # Public endpoint for Replicate webhook events (start/output/completed)
    status = payload.get("status")
    pid = payload.get("id")
    print(f"[webhook/public] replicate status={status} id={pid}")
    return {"ok": True}
