from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from .config import settings
from .database import init_db, get_session
from .models import SKU, Frame
from .s3 import presign_put, public_url
from .webhooks import router as webhooks_router

app = FastAPI(title="SKU HeadSwap API")
app.include_router(webhooks_router)

origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"ok": True}

# ---------- Upload presigned URLs ----------
class UploadReq(BaseModel):
    files: list[dict]  # [{filename, size?}]

@app.post("/skus/{sku_code}/upload-urls")
def upload_urls(sku_code: str, body: UploadReq):
    urls = []
    for f in body.files:
        fname = f.get("filename", "file.jpg")
        key = f"skus/{sku_code}/raw/{fname}"
        signed = presign_put(key)
        urls.append({"filename": fname, "url": signed, "key": key, "public": public_url(key)})
    return {"urls": urls}

# ---------- Register frames after upload ----------
class FramesReq(BaseModel):
    files: list[dict]  # [{filename, key}]

@app.post("/skus/{sku_code}/frames")
def register_frames(sku_code: str, body: FramesReq):
    db = get_session()
    try:
        sku = db.execute(select(SKU).where(SKU.sku_code == sku_code)).scalar_one_or_none()
        if not sku:
            sku = SKU(sku_code=sku_code)
            db.add(sku)
            db.commit()
            db.refresh(sku)

        created = []
        for f in body.files:
            key = f["key"]
            raw_url = public_url(key)
            frame = Frame(sku_id=sku.id, filename=f["filename"], raw_url=raw_url, current_version=0)
            db.add(frame)
            db.commit()
            db.refresh(frame)
            created.append({"frame_id": frame.id, "raw_url": raw_url})
        return {"ok": True, "frames": created}
    finally:
        db.close()

# ---------- Start processing (mask + replicate) ----------
@app.post("/skus/{sku_code}/process")
def start_process(sku_code: str):
    # MVP-заглушка: просто вернём ok. В проде — ставим задания Celery.
    return {"ok": True, "message": "Processing started (mock)."}
