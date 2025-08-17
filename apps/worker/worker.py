# apps/worker/worker.py
import os, io, uuid, math, time
from celery import Celery
import httpx
import numpy as np
import cv2
from PIL import Image
import boto3
import mediapipe as mp

# --- ENV ---
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

S3_BUCKET  = os.environ["S3_BUCKET"]
S3_REGION  = os.environ.get("S3_REGION")              # у тебя us-east-2
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")           # чаще пусто для AWS
AWS_KEY    = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")

API_BASE_URL = os.environ.get("API_BASE_URL")         # https://api-backend-.../internal

# Replicate: можно либо указать конкретную версию,
# либо указать модель (owner/name) и пойдём через /v1/models/.../predictions
REPLICATE_API_TOKEN      = os.environ["REPLICATE_API_TOKEN"]
REPLICATE_MODEL          = os.environ.get("REPLICATE_MODEL")          # например: labprototypes/tnkfwm2
REPLICATE_MODEL_VERSION  = os.environ.get("REPLICATE_MODEL_VERSION")  # конкретный version id (опционально)

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
    # учитываем регион (для us-east-2 надо явный регион)
    region_part = f".s3.{S3_REGION}.amazonaws.com" if S3_REGION else ".s3.amazonaws.com"
    return f"https://{S3_BUCKET}{region_part}/{key}"

# --- IO helpers ---
def _download(url: str) -> np.ndarray:
    with httpx.Client(timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        img_arr = np.frombuffer(r.content, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Failed to decode image")
        return img

def _to_png_bytes(mask: np.ndarray) -> bytes:
    # гарантируем 8-битную L-маску
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    mask = np.where(mask >= 128, 255, 0).astype(np.uint8)
    pil = Image.fromarray(mask, mode="L")
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()

def put_mask_to_s3(key: str, mask_png: bytes):
    s3_client().put_object(Bucket=S3_BUCKET, Key=key, Body=mask_png, ContentType="image/png")
    return s3_url(key)

# --- Masking ---
def _expand_rect(x, y, w, h, expand_px, W, H):
    x2, y2 = x + w, y + h
    x = max(0, x - expand_px)
    y = max(0, y - expand_px)
    x2 = min(W, x2 + expand_px)
    y2 = min(H, y2 + expand_px)
    return int(x), int(y), int(x2 - x), int(y2 - y)

def _mask_by_haar(image_bgr: np.ndarray, expand_ratio: float = 0.10) -> np.ndarray:
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
        expand_px = int(W * expand_ratio)  # жёсткий край, просто расширяем
        x, y, w, h = _expand_rect(x, y, w, h, expand_px, W, H)
        mask[y:y+h, x:x+w] = 255
    return mask

def make_face_mask(image_bgr: np.ndarray, dilate_px: int = 24) -> np.ndarray:
    """
    MediaPipe Face Mesh -> face oval -> бинарная маска с жёстким краем
    При ошибке/отсутствии лица — фолбэк на Haar.
    """
    H, W = image_bgr.shape[:2]
    try:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=False) as fm:
            res = fm.process(image_rgb)

        if not res.multi_face_landmarks:
            return _mask_by_haar(image_bgr, expand_ratio=0.10)

        lm = res.multi_face_landmarks[0]

        # стандартные индексы овала лица
        face_oval_idx = [
            10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
            397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
            172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109
        ]
        pts = []
        for idx in face_oval_idx:
            x = int(lm.landmark[idx].x * W)
            y = int(lm.landmark[idx].y * H)
            pts.append([x, y])
        pts = np.array(pts, dtype=np.int32)

        mask = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)

        if dilate_px and dilate_px > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*dilate_px+1, 2*dilate_px+1))
            mask = cv2.dilate(mask, k)

        mask = np.where(mask >= 128, 255, 0).astype(np.uint8)
        return mask
    except Exception:
        # на всякий случай не роняем воркер
        return _mask_by_haar(image_bgr, expand_ratio=0.10)

# --- Replicate ---
def replicate_predict(input_dict: dict) -> dict:
    """
    Делает запрос на Replicate:
    - если задан REPLICATE_MODEL_VERSION — используем /v1/predictions + version
    - иначе используем маршрут /v1/models/{owner}/{name}/predictions
    Возвращает JSON старта предикшна.
    """
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    if REPLICATE_MODEL_VERSION:
        url = "https://api.replicate.com/v1/predictions"
        payload = {"version": REPLICATE_MODEL_VERSION, "input": input_dict}
    else:
        assert REPLICATE_MODEL, "REPLICATE_MODEL or REPLICATE_MODEL_VERSION must be set"
        url = f"https://api.replicate.com/v1/models/{REPLICATE_MODEL}/predictions"
        payload = {"input": input_dict}

    r = httpx.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code >= 400:
        # покажем тело ошибки для быстрой отладки 4xx/5xx (в т.ч. 422)
        raise httpx.HTTPStatusError(f"{r.status_code} {r.text}", request=r.request, response=r)
    return r.json()

def replicate_poll_until_done(start_json: dict, timeout_sec: int = 180, interval_sec: float = 1.0) -> dict:
    """
    Поллинг статуса до 'succeeded/failed/canceled'
    """
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    poll_url = start_json["urls"]["get"]
    t0 = time.time()
    last = start_json
    while time.time() - t0 < timeout_sec:
        r = httpx.get(poll_url, headers=headers, timeout=30)
        r.raise_for_status()
        last = r.json()
        st = last.get("status")
        if st in ("succeeded", "failed", "canceled"):
            break
        time.sleep(interval_sec)
    return last

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

    # 2) определяем откуда брать исходник
    sku_code = info["sku"]["code"]
    original_url = info.get("original_url")
    original_key = info.get("original_key")

    if not original_url and original_key:
        # private bucket → генерим presigned GET на 1 час
        original_url = s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": original_key},
            ExpiresIn=3600,
        )
    if not original_url:
        raise RuntimeError("No original_url or original_key to generate source URL")

    # 3) маска (жёсткий край, расширение ~24px)
    img = _download(original_url)
    mask = make_face_mask(img, dilate_px=24)
    mask_png = _to_png_bytes(mask)
    mask_key = f"masks/{sku_code}/{frame_id}.png"
    put_mask_to_s3(mask_key, mask_png)
    mask_url = s3_url(mask_key)

    # 4) промпт (профиль головы — 'Маша' по умолчанию)
    token = (info.get("head") or {}).get("trigger_token", "tnkfwm1")
    prompt_tmpl = (info.get("head") or {}).get("prompt_template", "a photo of {token} female model")
    prompt = prompt_tmpl.format(token=token)

    # 5) параметры генерации — по ТЗ
    input_dict = {
        "prompt": prompt,
        "image": original_url,
        "mask": mask_url,
        "prompt_strength": 0.8,
        "num_outputs": 3,
        "num_inference_steps": 50,
        "guidance_scale": 2.5,
        "output_format": "png",
        "model": "dev",
    }

    # 6) запускаем Replicate и ждём результата
    started = replicate_predict(input_dict)
    done = replicate_poll_until_done(started, timeout_sec=240, interval_sec=1.0)

    if done.get("status") != "succeeded":
        # зарегистрируем факт неуспеха (без падения воркера — опционально можно падать)
        try:
            with httpx.Client(timeout=30) as c:
                c.post(
                    f"{API_BASE_URL}/internal/frame/{frame_id}/generation",
                    json={"replicate_id": started.get("id"), "status": done.get("status"), "error": done},
                )
        finally:
            raise RuntimeError(f"Replicate failed: {done}")

    output_urls = done.get("output", []) or []
    replicate_id = done.get("id")

    # 7) регистрируем генерацию на API (теперь с реальным replicate_id и outputs)
    with httpx.Client(timeout=60) as c:
        reg = c.post(
            f"{API_BASE_URL}/internal/frame/{frame_id}/generation",
            json={"replicate_id": replicate_id, "outputs": output_urls, "status": "succeeded"},
        )
        reg.raise_for_status()
