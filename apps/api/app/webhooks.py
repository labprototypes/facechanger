from fastapi import APIRouter, Request, HTTPException
import hmac, hashlib, json, asyncio
from sqlalchemy.orm import joinedload
from .config import settings
from .database import db_session
from .models import Generation, GenStatus, Frame, FrameStatus, SKU
from .s3util import upload_from_url, output_key

router = APIRouter(prefix="/webhooks")

def verify(req: Request, body: bytes):
    sig = req.headers.get("X-Replicate-Signature", "")
    mac = hmac.new(settings.replicate_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, mac)

@router.post("/replicate")
async def replicate_webhook(request: Request):
    body = await request.body()
    if settings.replicate_webhook_secret and not verify(request, body):
        raise HTTPException(403, "bad signature")

    payload = json.loads(body.decode())
    # структура Replicate: {id, status, input, output, error, urls: {...}, ...}
    pred_id = payload.get("id")
    status = payload.get("status")
    meta = payload.get("input", {})
    frame_id = int(meta.get("frame_id", 0))  # мы передавали его в input

    db = db_session()
    gen = db.query(Generation).filter(Generation.replicate_prediction_id == pred_id).first()
    if not gen:
        # запасной вариант: ищем по frame_id последний RUNNING
        gen = db.query(Generation).filter(Generation.frame_id == frame_id, Generation.status == GenStatus.RUNNING).first()
        if not gen:
            return {"ok": True}  # нечего обновлять

    if status == "succeeded" or status == "completed":
        out_urls = payload.get("output") or []
        if not isinstance(out_urls, list): out_urls = [out_urls]
        # складываем в S3
        fr = db.query(Frame).join(SKU).filter(Frame.id == gen.frame_id).first()
        saved_keys = []
        for i, u in enumerate(out_urls):
            key = output_key(fr.sku.code, fr.id, pred_id, i)
            url = await upload_from_url(key, u)
            saved_keys.append(key)
        gen.output_keys = saved_keys
        gen.status = GenStatus.COMPLETED
        fr.status = FrameStatus.DONE
        db.commit()
    elif status in ("failed", "canceled"):
        gen.status = GenStatus.FAILED
        gen.error = payload.get("error") or "failed"
        fr = db.query(Frame).filter(Frame.id == gen.frame_id).first()
        if fr: fr.status = FrameStatus.FAILED
        db.commit()
    else:
        gen.status = GenStatus.RUNNING
        db.commit()

    return {"ok": True}
