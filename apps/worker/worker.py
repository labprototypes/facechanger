import os
import io
import uuid
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from celery import Celery
import httpx
import numpy as np
import cv2
from PIL import Image
import boto3

# ======== ENV ========
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")

API_BASE_URL = os.environ["API_BASE_URL"]  # например: https://api-backend-xxx.onrender.com

# Replicate
REPLICATE_API_TOKEN = os.environ["REPLICATE_API_TOKEN"]
# используем именно версию модели (строка версии из Replicate UI)
REPLICATE_MODEL_VERSION = os.environ["REPLICATE_MODEL_VERSION"]

# Маска: насколько расширять прямоугольник лица (меньше — уже маска)
MASK_EXPAND_RATIO = float(os.environ.get("MASK_EXPAND_RATIO", "0.06"))  # было 0.10

# ======== Celery ========
celery = Celery("worker", broker=REDIS_URL, backend=REDIS_URL)


# ======== S3 helpers ========
def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=AWS_KEY or None,
        aws_secret_access_key=AWS_SECRET or None,
    )


def s3_public_url(key: str) -> str:
    # Универсальная публичная форма (как в бэке)
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"


def s3_put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream"):
    s3_client().put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    return s3_public_url(key)

def s3_key_from_public_url(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        path = p.path.lstrip("/")
        if not host or not path:
            return None
        if host == f"{S3_BUCKET}.s3.amazonaws.com" or host == f"{S3_BUCKET}.s3.{(S3_REGION or '').lower()}.amazonaws.com":
            return path
        if host.startswith("s3.") and host.endswith(".amazonaws.com"):
            parts = path.split("/", 1)
            if len(parts) == 2 and parts[0] == S3_BUCKET:
                return parts[1]
        if host.endswith(".s3.amazonaws.com") and host.split(".")[0] == S3_BUCKET:
            return path
        return None
    except Exception:
        return None

def ensure_presigned_download(url: Optional[str], key: Optional[str]) -> str:
    """
    Возвращает URL, доступный извне (Replicate):
    - если уже presigned (есть X-Amz-Algorithm/Signature) — вернёт как есть
    - иначе сгенерит presigned по переданному key либо извлечённому из url
    - если это вообще не S3-URL и без key — вернёт исходный url как есть
    """
    if url and ("X-Amz-Algorithm=" in url or "X-Amz-Signature=" in url):
        return url
    k = key
    if not k and url:
        k = s3_key_from_public_url(url)
    if k:
        return s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": k},
            ExpiresIn=3600,
        )
    if url:
        return url
    raise ValueError("ensure_presigned_download: neither url nor key provided")

# ======== IO helpers ========
def http_get_bytes(url: str, timeout: int = 60) -> bytes:
    with httpx.Client(timeout=timeout) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def http_get_image_bgr(url: str, timeout: int = 60) -> np.ndarray:
    raw = http_get_bytes(url, timeout=timeout)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("Failed to decode image from bytes")
    return img


def png_bytes_from_array(mask: np.ndarray) -> bytes:
    pil = Image.fromarray(mask)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


# ======== Masking ========
def _expand_rect(x: int, y: int, w: int, h: int, expand_px: int, W: int, H: int):
    x2, y2 = x + w, y + h
    x = max(0, x - expand_px)
    y = max(0, y - expand_px)
    x2 = min(W, x2 + expand_px)
    y2 = min(H, y2 + expand_px)
    return int(x), int(y), int(x2 - x), int(y2 - y)


def make_face_mask(image_bgr: np.ndarray, expand_ratio: float) -> np.ndarray:
    H, W = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Стандартный каскад лиц из OpenCV
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64))

    mask = np.zeros((H, W), dtype=np.uint8)
    if len(faces) == 0:
        # Фолбек (центр, чтобы не падать): примерно область головы
        w = int(W * 0.22)
        h = int(H * 0.32)
        x = W // 2 - w // 2
        y = H // 4
        faces = [(x, y, w, h)]

    for (x, y, w, h) in faces:
        expand_px = int(W * expand_ratio)  # Жёсткий край — прямоугольник
        x, y, w, h = _expand_rect(x, y, w, h, expand_px, W, H)
        mask[y:y + h, x:x + w] = 255

    return mask


# ======== Replicate ========
def replicate_create_prediction(inp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Создаёт prediction на Replicate. Обязательно передаём version.
    Возвращает JSON от Replicate (должны быть поля id, status, urls.get).
    """
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "version": REPLICATE_MODEL_VERSION,
        "input": inp,
    }
    r = httpx.post(
        "https://api.replicate.com/v1/predictions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    if r.status_code >= 400:
        # Логируем понятную ошибку
        try:
            err = r.json()
        except Exception:
            err = {"raw": r.text}
        raise RuntimeError(f"Replicate create error {r.status_code}: {err}")
    return r.json()


def replicate_poll(get_url: str, max_wait_sec: int = 600, step_sec: float = 2.5) -> Dict[str, Any]:
    """
    Ждём завершения предикта. Возвращаем финальный JSON.
    """
    headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
    waited = 0.0
    while True:
        r = httpx.get(get_url, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status in ("succeeded", "failed", "canceled"):
            return data
        import time
        time.sleep(step_sec)
        waited += step_sec
        if waited >= max_wait_sec:
            raise TimeoutError("Replicate polling timeout")


# ======== Helpers: fetch original with presign fallback ========
def fetch_source_image_bgr(original_url: str, original_key: Optional[str]) -> np.ndarray:
    """
    Сначала пробуем скачать original_url.
    Если 401/403/404 и нет original_key — пробуем извлечь key из URL.
    Затем делаем presigned GET и повторяем скачивание.
    """
    try:
        return http_get_image_bgr(original_url)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else None
        if code in (401, 403, 404):
            key = original_key or s3_key_from_public_url(original_url)
            if key:
                presigned = s3_client().generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_BUCKET, "Key": key},
                    ExpiresIn=3600,
                )
                # лог для отладки
                print(f"[worker] S3 {code} on direct URL — retry with presigned for key={key}")
                return http_get_image_bgr(presigned)
        # если сюда дошли — фолбэк невозможен
        raise

def s3_key_from_public_url(url: str) -> Optional[str]:
    """
    Пытаемся достать Key из публичного S3 URL:
    - https://<bucket>.s3.amazonaws.com/<key>
    - https://<bucket>.s3.<region>.amazonaws.com/<key>
    - https://s3.<region>.amazonaws.com/<bucket>/<key>  (на всякий)
    """
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        path = p.path.lstrip("/")
        if not host or not path:
            return None

        # Виртуальный хостинг: <bucket>.s3.amazonaws.com / <bucket>.s3.<region>.amazonaws.com
        if host == f"{S3_BUCKET}.s3.amazonaws.com" or host == f"{S3_BUCKET}.s3.{(S3_REGION or '').lower()}.amazonaws.com":
            return path

        # Путь-стиль: s3.<region>.amazonaws.com/<bucket>/<key>
        if host.startswith("s3.") and host.endswith(".amazonaws.com"):
            parts = path.split("/", 1)
            if len(parts) == 2 and parts[0] == S3_BUCKET:
                return parts[1]

        # Ещё один вариант виртуального хоста (без region в host)
        if host.endswith(".s3.amazonaws.com") and host.split(".")[0] == S3_BUCKET:
            return path

        return None
    except Exception:
        return None

# ======== Tasks ========
@celery.task(name="worker.process_sku")
def process_sku(sku_id: int):
    """
    На вход приходит внутренний sku_id (int).
    Тянем список кадров и ставим их в очередь.
    """
    assert API_BASE_URL, "API_BASE_URL env is required"
    url = f"{API_BASE_URL}/internal/sku/{sku_id}/frames"
    with httpx.Client(timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        data = r.json()

    frames = data.get("frames", [])
    # Лог для отладки: покажем, что кладём в очередь
    try:
        print(f"[worker] enqueue frames for sku {sku_id}: {[f.get('id') for f in frames]}")
    except Exception:
        print(f"[worker] enqueue frames for sku {sku_id}: {frames}")

    for fr in frames:
        fid = fr["id"] if isinstance(fr, dict) else int(fr)
        process_frame.delay(int(fid))


@celery.task(name="worker.process_frame")
def process_frame(frame_id: int):
    """
    Полный пайплайн:
    - тянем фрейм
    - скачиваем original_url (если приватно — делаем presigned по original_key)
    - строим маску и грузим её в S3
    - регистрируем генерацию на бэке
    - создаём prediction на Replicate, сохраняем prediction_id
    - ждём завершения и грузим результат(ы) в S3
    """
    assert API_BASE_URL, "API_BASE_URL env is required"

    # 1) инфо о фрейме
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_BASE_URL}/internal/frame/{frame_id}")
        r.raise_for_status()
        info = r.json()

    sku = info.get("sku") or {}
    sku_code = str(sku.get("code") or f"sku_{sku.get('id', 'unknown')}")

    original_url: Optional[str] = info.get("original_url")
    original_key: Optional[str] = info.get("original_key")

    if not original_url and original_key:
        # Бэкенд не дал URL — генерим presigned
        original_url = s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": original_key},
            ExpiresIn=3600,
        )
    if not original_url:
        raise RuntimeError("Frame has no original_url or original_key")

    # 2) маска -> в S3 (с фолбэком presigned при необходимости)
    mask_key = f"masks/{sku_code}/{frame_id}.png"
    img = _download(original_url)
    mask = make_face_mask(img, expand_ratio=0.10)
    mask_png = _to_png_bytes(mask)
    put_mask_to_s3(mask_key, mask_png)

    image_url_for_model = ensure_presigned_download(original_url, original_key)
    mask_url_for_model  = ensure_presigned_download(None, mask_key)

    # 3) промпт (дефолтная "Маша" если профиля нет)
    head = info.get("head") or {}
    token = head.get("trigger_token") or "tnkfwm1"
    tmpl = head.get("prompt_template") or "a photo of {token} female model"
    prompt = str(tmpl).replace("{token}", token)

    # 4) регистрируем генерацию в бэке
    with httpx.Client(timeout=60) as c:
        reg = c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/generation", json={})
        reg.raise_for_status()
        reg_json = reg.json()
    generation_id = reg_json.get("id")
    if not generation_id:
        raise RuntimeError("internal generation create returned no id")

    # 5) делаем prediction на Replicate
    input_dict = {
        "prompt": prompt,
        "prompt_strength": 0.8,
        "num_outputs": 3,
        "num_inference_steps": 28,        # если используешь dev-версию модели
        "guidance_scale": 3,
        "output_format": "png",
        "image": image_url_for_model,     # ← теперь presigned
        "mask": mask_url_for_model,       # ← теперь presigned
        # при необходимости остальные поля (replicate_weights и т.п.)
    }

    pred = replicate_create_prediction(inp)
    pred_id = pred.get("id")
    pred_get = (pred.get("urls") or {}).get("get")
    if not pred_id or not pred_get:
        raise RuntimeError(f"Replicate create response missing fields: {pred}")

    # 6) сохраняем prediction_id в бэке
    with httpx.Client(timeout=60) as c:
        r = c.post(
            f"{API_BASE_URL}/internal/generation/{generation_id}/prediction",
            json={"prediction_id": pred_id},
        )
        r.raise_for_status()

    # 7) ждём завершения
    final = replicate_poll(pred_get)
    status = final.get("status")
    if status != "succeeded":
        print(f"[worker] replicate prediction {pred_id} finished with status={status}, detail={final}")
        return

    # 8) выгружаем результаты в S3
    outputs: List[str] = []
    raw_outputs = final.get("output") or []
    if not isinstance(raw_outputs, list):
        raw_outputs = [raw_outputs] if raw_outputs else []

    for i, out_url in enumerate(raw_outputs):
        try:
            content = http_get_bytes(out_url, timeout=120)
            # определим расширение по URL (если нет — png)
            parsed = urlparse(out_url)
            name = os.path.basename(parsed.path) or f"out_{i}.png"
            ext = os.path.splitext(name)[1].lower() or ".png"
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".png"
            key = f"outputs/{sku_code}/{frame_id}/{pred_id[:8]}_{i}{ext}"
            # эвристика контента
            ctype = (
                "image/png" if ext == ".png"
                else "image/jpeg" if ext in (".jpg", ".jpeg")
                else "image/webp" if ext == ".webp"
                else "application/octet-stream"
            )
            url = s3_put_bytes(key, content, content_type=ctype)
            outputs.append(url)
        except Exception as e:
            print(f"[worker] failed to upload output {i} to S3: {e}")

    print(f"[worker] frame {frame_id}: uploaded {len(outputs)} outputs to S3")
