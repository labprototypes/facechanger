import os
import io
import uuid
from typing import Dict, Any, List

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

API_BASE_URL = os.environ.get("API_BASE_URL")  # базовый URL бэка
REPLICATE_TOKEN = os.environ.get("REPLICATE_API_TOKEN")            # Token ****
REPLICATE_MODEL_VERSION = os.environ.get("REPLICATE_MODEL_VERSION")  # версия tnKFWM2 (желательно задать)
REPLICATE_MODEL = os.environ.get("REPLICATE_MODEL")                  # fallback: owner/model (например labprototypes/tnkfwm2)

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

def s3_url(key: str) -> str:
    # публичный URL стандартного endpoint
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"

# --- IO helpers ---
def _download(url: str) -> np.ndarray:
    with httpx.Client(timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        img_arr = np.frombuffer(r.content, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("cv2.imdecode failed for downloaded image")
        return img

def _to_png_bytes(mask: np.ndarray) -> bytes:
    pil = Image.fromarray(mask)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()

# --- Masking (OpenCV Haar + жёсткий край, расширение) ---
def _expand_rect(x, y, w, h, expand_px, W, H):
    x2, y2 = x + w, y + h
    x = max(0, x - expand_px)
    y = max(0, y - expand_px)
    x2 = min(W, x2 + expand_px)
    y2 = min(H, y2 + expand_px)
    return int(x), int(y), int(x2 - x), int(y2 - y)

def make_face_mask(image_bgr: np.ndarray, expand_ratio: float = 0.10, dilate_px: int = 0) -> np.ndarray:
    H, W = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64))

    mask = np.zeros((H, W), dtype=np.uint8)

    if len(faces) == 0:
        # fallback: прямоугольник по центру верхней половины
        w = int(W * 0.25)
        h = int(H * 0.35)
        x = W // 2 - w // 2
        y = max(0, H // 4 - h // 4)
        faces = [(x, y, w, h)]

    for (x, y, w, h) in faces:
        expand_px = int(W * expand_ratio)
        x, y, w, h = _expand_rect(x, y, w, h, expand_px, W, H)
        mask[y:y + h, x:x + w] = 255  # ЖЁСТКИЙ край

    if dilate_px and dilate_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate_px + 1, 2 * dilate_px + 1))
        mask = cv2.dilate(mask, k)
        mask = np.where(mask >= 128, 255, 0).astype(np.uint8)

    return mask

def put_mask_to_s3(key: str, mask_png: bytes):
    s3_client().put_object(Bucket=S3_BUCKET, Key=key, Body=mask_png, ContentType="image/png")
    return s3_url(key)

# --- Replicate ---
def replicate_predict(input_dict: dict) -> dict:
    import httpx, json

    if not REPLICATE_TOKEN:
        raise RuntimeError("REPLICATE_API_TOKEN is not set")

    headers = {
        "Authorization": f"Token {REPLICATE_TOKEN}",  # именно Token
        "Content-Type": "application/json",
    }

    # Если есть конкретная версия — используем универсальный endpoint
    if REPLICATE_MODEL_VERSION:
        url = "https://api.replicate.com/v1/predictions"
        payload = {"version": REPLICATE_MODEL_VERSION, "input": input_dict}

    # Иначе, если задали только модель (owner/name) — используем модельный endpoint
    elif REPLICATE_MODEL:
        url = f"https://api.replicate.com/v1/models/{REPLICATE_MODEL}/predictions"
        payload = {"input": input_dict}

    else:
        raise RuntimeError("Set REPLICATE_MODEL_VERSION or REPLICATE_MODEL in environment")

    r = httpx.post(url, headers=headers, json=payload, timeout=120)
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = {"raw": r.text}
        raise RuntimeError(f"Replicate API error {r.status_code}: {detail}")
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

    # 1) тянем описание кадра с API
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_BASE_URL}/internal/frame/{frame_id}")
        r.raise_for_status()
        info = r.json()

    # 2) URL исходника
    original_url = info.get("original_url")
    original_key = info.get("original_key")
    sku_code = info["sku"]["code"]

    if not original_url and original_key:
        # приватный бакет → делаем presigned GET
        original_url = s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": original_key},
            ExpiresIn=3600,
        )

    if not original_url:
        raise RuntimeError("No original_url or original_key provided for frame")

    # 3) делаем маску (жёсткий край, +10% ширины)
    mask_key = f"masks/{sku_code}/{frame_id}.png"
    img = _download(original_url)
    mask = make_face_mask(img, expand_ratio=0.10, dilate_px=0)
    mask_png = _to_png_bytes(mask)
    put_mask_to_s3(mask_key, mask_png)
    mask_url = s3_url(mask_key)

    # 4) собираем промпт (профиль головы "Маша" по умолчанию)
    token = (info.get("head") or {}).get("trigger_token", "tnkfwm1")
    prompt_tmpl = (info.get("head") or {}).get("prompt_template", "a photo of {token} female model")
    prompt = prompt_tmpl.replace("{token}", token)

    # 5) параметры генерации — по ТЗ
    input_dict = {
        "prompt": prompt,
        "prompt_strength": 0.8,
        "num_outputs": 3,
        "num_inference_steps": 50,
        "guidance_scale": 2.5,
        "output_format": "png",
        "image": original_url,
        "mask": mask_url,
    }

    # 6) регистрируем поколение на API (для трекинга)
    with httpx.Client(timeout=60) as c:
        reg = c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/generation", json={})
        reg.raise_for_status()
        gen_id = reg.json()["id"]

    # 7) шлём в Replicate
    pred = replicate_predict(input_dict)

    # 8) сохраняем prediction_id на API
    with httpx.Client(timeout=60) as c:
        c.post(
            f"{API_BASE_URL}/internal/generation/{gen_id}/prediction",
            json={"prediction_id": pred["id"]},
        )
