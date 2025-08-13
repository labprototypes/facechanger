from fastapi import APIRouter, Request, HTTPException
from .config import settings
from .security import verify_signature

router = APIRouter()

@router.post("/webhooks/replicate")
async def replicate_webhook(request: Request):
    # 1) Проверяем подпись
    raw = await request.body()
    sig = request.headers.get("X-Replicate-Signature")
    if not verify_signature(settings.replicate_webhook_secret, raw, sig):
        raise HTTPException(status_code=401, detail="invalid signature")

    # 2) Парсим полезную нагрузку
    payload = await request.json()
    # Примеры полей, которые обычно приходят от Replicate:
    # id, status (starting|processing|succeeded|failed|canceled), output, error, logs, metrics, etc.
    # TODO: здесь — найти по id нашу Version/Output и обновить БД

    # Для отладки просто вернём ok
    return {"ok": True}
