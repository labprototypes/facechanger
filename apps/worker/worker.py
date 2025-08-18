import os, io, time
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

REPLICATE_TOKEN = os.environ["REPLICATE_API_TOKEN"]
REPLICATE_MODEL_VERSION = os.environ.get("REPLICATE_MODEL_VERSION")
API_BASE_URL = os.environ.get("API_BASE_URL")

MASK_EXPAND_RATIO = float(os.environ.get("MASK_EXPAND_RATIO", "0.06"))

celery = Celery("worker", broker=REDIS_URL, backend=REDIS_URL)

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

def _download(url: str) -> np.ndarray:
    with httpx.Client(timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        img_arr = np.frombuffer(r.content, dtype=np.uint8)
        return cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

def _to_png_bytes(mask: np.ndarray) -> bytes:
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(mask.astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue()

def _expand_rect(x, y, w, h, expand_px, W, H):
    x2, y2 = x + w, y + h
    x = max(0, x - expand_px); y = max(0, y - expand_px)
    x2 = min(W, x2 + expand_px); y2 = min(H, y2 + expand_px)
    return int(x), int(y), int(x2 - x), int(y2 - y)

def make_face_mask(image_bgr: np.ndarray, expand_ratio: float = MASK_EXPAND_RATIO) -> np.ndarray:
    H, W = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64))
    mask = np.zeros((H, W), dtype=np.uint8)
    if len(faces) == 0:
        w = int(W * 0.22); h = int(H * 0.32)
        x = W // 2 - w // 2; y = H // 4
        faces = [(x, y, w, h)]
    for (x, y, w, h) in faces:
        expand_px = int(W * expand_ratio)
        x, y, w, h = _expand_rect(x, y, w, h, expand_px, W, H)
        mask[y:y+h, x:x+w] = 255
    return mask

def put_mask_to_s3(key: str, mask_png: bytes):
    s3_client().put_object(Bucket=S3_BUCKET, Key=key, Body=mask_png, ContentType="image/png")
    return s3_url(key)

def replicate_predict(input_dict: dict) -> dict:
    if not REPLICATE_MODEL_VERSION:
        raise RuntimeError("REPLICATE_MODEL_VERSION env var is required")
    headers = {
        "Authorization": f"Token {REPLICATE_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"version": REPLICATE_MODEL_VERSION, "input": input_dict}
    with httpx.Client(timeout=60) as c:
        r = c.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        if r.status_code >= 400:
            try:
                err = r.json()
            except Exception:
                err = {"raw": r.text}
            raise RuntimeError(f"Replicate API error {r.status_code}: {err}")
        return r.json()

def replicate_poll(prediction_id: str) -> dict:
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    with httpx.Client(timeout=60) as c:
        while True:
            r = c.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
            r.raise_for_status()
            data = r.json()
            if data.get("status") in ("succeeded", "failed", "canceled"):
                return data
            time.sleep(2)

@celery.task(name="worker.process_sku")
def process_sku(sku_id: int):
    if not API_BASE_URL:
        print("WARN: API_BASE_URL is not set; cannot fetch frames.")
        return

    # 1) тянем список кадров
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_BASE_URL}/internal/sku/{sku_id}/frames")
        r.raise_for_status()
        data = r.json()

    # 2) нормализуем payload: поддерживаем {"frames":[{"id":1}, ...]},
    #    {"frames":[1,2,...]} и {"items":[...]}
    frames_payload = data.get("frames")
    if frames_payload is None:
        frames_payload = data.get("items", [])

    frame_ids: list[int] = []
    for item in frames_payload:
        if isinstance(item, dict):
            fid = item.get("id") or item.get("frame_id") or item.get("frameId")
        else:
            fid = item
        if fid is None:
            continue
        s = str(fid)
        try:
            fid_int = int(s.split("_")[-1])  # допускаем "fr_1"
        except Exception:
            continue
        frame_ids.append(fid_int)

    print(f"[worker] enqueue frames for sku {sku_id}: {frame_ids}")
    for fid in frame_ids:
        process_frame.delay(fid)

@celery.task(name="worker.process_frame")
def process_frame(frame_id: int):
    assert API_BASE_URL, "API_BASE_URL required for worker"

    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_BASE_URL}/internal/frame/{frame_id}")
        r.raise_for_status()
        info = r.json()

    sku_code = info["sku"]["code"]
    original_url = info.get("original_url")
    original_key = info.get("original_key")

    if not original_url and original_key:
        original_url = s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": original_key},
            ExpiresIn=3600,
        )

    mask_key = f"masks/{sku_code}/fr_{frame_id}.png"
    img = _download(original_url)
    mask = make_face_mask(img, expand_ratio=MASK_EXPAND_RATIO)
    mask_png = _to_png_bytes(mask)
    put_mask_to_s3(mask_key, mask_png)
    mask_url = s3_url(mask_key)

    token = (info.get("head") or {}).get("trigger_token", "tnkfwm1")
    tmpl = (info.get("head") or {}).get("prompt_template", "a photo of {token} female model")
    prompt = tmpl.replace("{token}", token)

    with httpx.Client(timeout=60) as c:
        reg = c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/generation", json={})
        reg.raise_for_status()
        gen_id = reg.json()["id"]

    input_dict = {
        "prompt": prompt,
        "image": original_url,
        "mask": mask_url,
        "prompt_strength": 0.8,
        "num_outputs": 3,
        "num_inference_steps": 28,
        "guidance_scale": 3,
        "output_format": "png",
    }
    pred = replicate_predict(input_dict)
    prediction_id = pred["id"]

    with httpx.Client(timeout=60) as c:
        c.post(f"{API_BASE_URL}/internal/generation/{gen_id}/prediction", json={"prediction_id": prediction_id})

    final = replicate_poll(prediction_id)
    status = final.get("status")
    if status == "succeeded":
        outputs = final.get("output") or []
        with httpx.Client(timeout=60) as c:
            c.post(f"{API_BASE_URL}/internal/generation/{gen_id}/result", json={"urls": outputs})
    else:
        with httpx.Client(timeout=60) as c:
            c.post(
                f"{API_BASE_URL}/internal/generation/{gen_id}/status",
                json={"status": status, "error": final.get("error")},
            )
