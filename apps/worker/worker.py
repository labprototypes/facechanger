# apps/worker/worker.py
import os
import io
import uuid
from celery import Celery
import httpx
import numpy as np
import cv2
from PIL import Image
import boto3

# --- ENV ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")

API_BASE_URL = os.environ.get("API_BASE_URL")  # база для /internal ручек бэка

REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
REPLICATE_MODEL_VERSION = os.environ["REPLICATE_MODEL_VERSION"]  # строго owner/model:version или UUID версии

# --- Celery app ---
celery = Celery("worker", broker=REDIS_URL, backend=REDIS_URL)

# --- S3 helpers ---
def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=AWS_KEY or None,
        aws_secret_access_key=AWS_SECRET or None,
    )

def s3_presigned_get(key: str, expires: int = 3600) -> str:
    """Безопасная ссылка на приватный объект — то, что надо отдавать в Replicate/UI."""
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )

def put_bytes(key: str, data: bytes, content_type: str):
    # Объект остаётся приватным (ACL не трогаем) — будем раздавать presigned GET.
    s3_client().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )

# --- IO helpers ---
def _download(url: str) -> np.ndarray:
    with httpx.Client(timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        arr = np.frombuffer(r.content, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def _to_png_bytes(mask: np.ndarray) -> bytes:
    pil = Image.fromarray(mask)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()

# --- Masking ---
def _expand_rect(x, y, w, h, expand_px, W, H):
    x2, y2 = x + w, y + h
    x = max(0, x - expand_px)
    y = max(0, y - expand_px)
    x2 = min(W, x2 + expand_px)
    y2 = min(H, y2 + expand_px)
    return int(x), int(y), int(x2 - x), int(y2 - y)

def make_face_mask(image_bgr: np.ndarray, expand_ratio: float = 0.10) -> np.ndarray:
    """Простая маска: жесткий bbox лица с запасом по ширине кадра (+10% по умолч.)."""
    H, W = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64)
    )
    mask = np.zeros((H, W), dtype=np.uint8)
    if len(faces) == 0:
        # fallback — примерный прямоугольник по центру
        w = int(W * 0.25)
        h = int(H * 0.35)
        x = W // 2 - w // 2
        y = H // 4
        faces = [(x, y, w, h)]
    for (x, y, w, h) in faces:
        expand_px = int(max(w, h) * expand_ratio)
        x, y, w, h = _expand_rect(x, y, w, h, expand_px, W, H)
        mask[y : y + h, x : x + w] = 255
    return mask

# --- Replicate ---
def replicate_predict(input_dict: dict) -> dict:
    """Запуск предсказания на Replicate c явной версией модели (иначе 422)."""
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",  # именно Token
        "Content-Type": "application/json",
    }
    payload = {"version": REPLICATE_MODEL_VERSION, "input": input_dict}
    with httpx.Client(timeout=60) as c:
        r = c.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        if r.status_code >= 400:
            # пробуем отдать понятную ошибку
            try:
                err = r.json()
            except Exception:
                err = {"raw": r.text}
            raise RuntimeError(f"Replicate API error {r.status_code}: {err}")
        return r.json()

# --- Tasks ---
@celery.task(name="worker.process_sku")
def process_sku(sku_id: int):
    if not API_BASE_URL:
        print("WARN: API_BASE_URL is not set; cannot fetch frames.")
        return
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_BASE_URL}/internal/sku/{sku_id}/frames")
        r.raise_for_status()
        data = r.json()
    for fr in data.get("frames", []):
        process_frame.delay(fr["id"])

@celery.task(name="worker.process_frame")
def process_frame(frame_id: int):
    assert API_BASE_URL, "API_BASE_URL required for worker"

    # 1) тянем описание кадра
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_BASE_URL}/internal/frame/{frame_id}")
        r.raise_for_status()
        info = r.json()

    sku_code = info["sku"]["code"]

    # 2) URL исходника (если ключ — делаем presigned GET)
    original_url = info.get("original_url")
    original_key = info.get("original_key")
    if not original_url and original_key:
        original_url = s3_presigned_get(original_key, 3600)

    # 3) делаем маску и кладём в S3 (объект приватный), берём presigned GET для Replicate
    img = _download(original_url)
    mask = make_face_mask(img, expand_ratio=0.20)
    mask_png = _to_png_bytes(mask)
    mask_key = f"masks/{sku_code}/{frame_id}.png"
    put_bytes(mask_key, mask_png, "image/png")
    mask_url = s3_presigned_get(mask_key, 3600)  # <<< КЛЮЧЕВАЯ ПРАВКА (был публичный URL)
    # сообщаем бэкенду, где лежит маска
    with httpx.Client(timeout=30) as c:
        c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/mask", json={"mask_key": mask_key})

    # 4) собираем промпт по профилю головы (дефолт «Маша»)
    head = info.get("head") or {}
    token = head.get("trigger_token", "tnkfwm1")
    prompt_tmpl = head.get("prompt_template", "a photo of {token} female model")
    prompt = prompt_tmpl.replace("{token}", token)

    # 5) регистрируем поколение на бэке (для трекинга)
    with httpx.Client(timeout=60) as c:
        reg = c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/generation", json={})
        reg.raise_for_status()
        gen_id = reg.json()["id"]

    # 6) отправляем задачу в Replicate
    input_dict = {
        "prompt": prompt,
        "image": original_url,
        "mask": mask_url,
        "prompt_strength": 0.8,
        "num_outputs": 3,
        "num_inference_steps": 28,
        "guidance_scale": 2.5,
        "output_format": "png",
    }
    pred = replicate_predict(input_dict)

    # --- ждём завершения у Replicate и сохраняем результаты ---
    pred_id = pred["id"]
    with httpx.Client(timeout=60) as c:
        # опрашиваем до готовности
        while True:
            pr = c.get(f"https://api.replicate.com/v1/predictions/{pred_id}",
                       headers={"Authorization": f"Token {REPLICATE_TOKEN}"} )
            pr.raise_for_status()
            pj = pr.json()
            st = pj.get("status")
            if st in ("succeeded", "failed", "canceled"):
                break
            time.sleep(2)
    
        if st == "succeeded":
            urls = pj.get("output") or []
            # сохраняем в бекенд
            c.post(f"{API_BASE_URL}/internal/generation/{gen_id}/result", json={"urls": urls})
            c.post(f"{API_BASE_URL}/internal/generation/{gen_id}/status", json={"status": "completed"})
        else:
            c.post(f"{API_BASE_URL}/internal/generation/{gen_id}/status",
                   json={"status": "failed", "error": pj.get("error")})
