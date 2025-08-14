import os, io, uuid, math
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

REPLICATE_TOKEN = os.environ["REPLICATE_API_TOKEN"]
REPLICATE_MODEL = os.environ["REPLICATE_MODEL"]  # owner/model:version
API_BASE_URL = os.environ.get("API_BASE_URL")    # нужен для /internal ручек API

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
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"

# --- IO helpers ---
def _download(url: str) -> np.ndarray:
    with httpx.Client(timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        img_arr = np.frombuffer(r.content, dtype=np.uint8)
        return cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

def _to_png_bytes(mask: np.ndarray) -> bytes:
    pil = Image.fromarray(mask)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()

# --- Masking ---
def _expand_rect(x, y, w, h, expand_px, W, H):
    x2, y2 = x + w, y + h
    x = max(0, x - expand_px); y = max(0, y - expand_px)
    x2 = min(W, x2 + expand_px); y2 = min(H, y2 + expand_px)
    return int(x), int(y), int(x2 - x), int(y2 - y)

def make_face_mask(image_bgr: np.ndarray, expand_ratio: float = 0.10) -> np.ndarray:
    H, W = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64))
    mask = np.zeros((H, W), dtype=np.uint8)
    if len(faces) == 0:
        # fallback: центр
        w = int(W * 0.25); h = int(H * 0.35)
        x = W // 2 - w // 2; y = H // 4
        faces = [(x, y, w, h)]
    for (x, y, w, h) in faces:
        expand_px = int(W * expand_ratio)  # +10% ширины кадра — ЖЁСТКИЙ край
        x, y, w, h = _expand_rect(x, y, w, h, expand_px, W, H)
        mask[y:y+h, x:x+w] = 255
    return mask

def put_mask_to_s3(key: str, mask_png: bytes):
    s3_client().put_object(Bucket=S3_BUCKET, Key=key, Body=mask_png, ContentType="image/png")
    return s3_url(key)

# --- Replicate ---
def parse_version_from_model(model: str) -> tuple[str, str]:
    # "owner/model:version" → ("owner/model", "version")
    if ":" in model:
        m, v = model.split(":", 1)
    else:
        m, v = model, ""
    return m, v

def replicate_predict(input_dict: dict):
    model, version = parse_version_from_model(REPLICATE_MODEL)
    payload = {"version": version, "input": input_dict}
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}", "Content-Type": "application/json"}
    with httpx.Client(timeout=120) as c:
        r = c.post("https://api.replicate.com/v1/predictions", json=payload, headers=headers)
        r.raise_for_status()
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
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_BASE_URL}/internal/frame/{frame_id}")
        r.raise_for_status()
        info = r.json()

    sku_code = info["sku"]["code"]
    original_url = info["original_url"]
    mask_key = f"masks/{sku_code}/{frame_id}.png"

    # 1) маска (жёсткий край, +10% ширины)
    img = _download(original_url)
    mask = make_face_mask(img, expand_ratio=0.10)
    mask_png = _to_png_bytes(mask)
    put_mask_to_s3(mask_key, mask_png)
    mask_url = s3_url(mask_key)

    # 2) промпт из профиля головы (Маша) или дефолт
    token = info["head"]["trigger_token"] if info.get("head") else "tnkfwm1"
    prompt = (info["head"]["prompt_template"] if info.get("head") else "a photo of {token} female model").replace("{token}", token)

    # 3) параметры генерации — по ТЗ
    input_dict = {
        "prompt": prompt,
        "prompt_strength": 0.8,
        "num_outputs": 3,
        "num_inference_steps": 50,
        "guidance_scale": 2.5,
        "output_format": "png",
        "image": original_url,
        "mask": mask_url,
        "frame_id": str(frame_id),  # вернётся во webhook payload.input
    }

    # регистрируем поколение на API
    with httpx.Client(timeout=60) as c:
        reg = c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/generation", json={})
        reg.raise_for_status()
        gen_id = reg.json()["id"]

    pred = replicate_predict(input_dict)

    # фиксируем prediction_id на API
    with httpx.Client(timeout=60) as c:
        c.post(f"{API_BASE_URL}/internal/generation/{gen_id}/prediction", json={"prediction_id": pred["id"]})
