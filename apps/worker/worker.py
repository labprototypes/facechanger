import os
import io
import uuid
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, unquote
from celery import Celery
import httpx
import numpy as np
import cv2
from PIL import Image
try:
    from ultralytics import YOLO  # YOLOv8
    _YOLO_MODEL_LOAD_ERROR = None
except Exception as e:  # ultralytics may not be installed yet
    YOLO = None
    _YOLO_MODEL_LOAD_ERROR = str(e)
import boto3
import re
try:
    from .head_mask import generate_head_mask_auto  # package import
except Exception:
    from head_mask import generate_head_mask_auto  # fallback when not recognized as pkg

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

# Опциональная сегментация головы через отдельную модель (lang-segment-anything)
HEAD_SEGMENT_MODEL_VERSION = os.environ.get("HEAD_SEGMENT_MODEL_VERSION")  # e.g. tmappdev/lang-segment-anything:<version_sha>
HEAD_SEGMENT_TEXT_PROMPT = os.environ.get("HEAD_SEGMENT_TEXT_PROMPT", "Head")

# Маска: насколько расширять прямоугольник лица (меньше — уже маска)
MASK_EXPAND_RATIO = float(os.environ.get("MASK_EXPAND_RATIO", "0.06"))  # base expand (will add head heuristics)
YOLO_FACE_MODEL = os.environ.get("YOLO_FACE_MODEL", "yolov8n-face.pt")  # custom lightweight face model path/name
_YOLO_FACE = None

def _get_yolo_face_model():
    global _YOLO_FACE
    if _YOLO_FACE is not None:
        return _YOLO_FACE
    if YOLO is None:
        return None
    try:
        _YOLO_FACE = YOLO(YOLO_FACE_MODEL)
    except Exception as e:
        print(f"[worker] failed to load YOLO face model: {e}")
        _YOLO_FACE = None
    return _YOLO_FACE

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

def s3_key_from_url(url: str) -> str | None:
    """Достаём S3 key из https://bucket.s3.amazonaws.com/<key>"""
    try:
        p = urlparse(url)
        key = unquote(p.path.lstrip("/"))  # '/uploads/..' -> 'uploads/..'
        return key or None
    except Exception:
        return None

def _extract_key_from_s3_url(url: str) -> Optional[str]:
    """
    Пытается достать S3 key из публичного/статического URL (AWS или MinIO-style).
    Поддерживает:
      - https://<bucket>.s3.<region>.amazonaws.com/<key>
      - https://s3.<region>.amazonaws.com/<bucket>/<key>
      - https://<endpoint>/<bucket>/<key>  (MinIO/кастом)
    """
    if not url: 
        return None
    u = urlparse(url)
    host = u.netloc
    path = u.path.lstrip("/")

    # pattern 1: bucket.s3.region.amazonaws.com/key
    m = re.match(rf"^{re.escape(S3_BUCKET)}\.s3\.[^/]+\.amazonaws\.com$", host)
    if m:
        return path or None

    # pattern 2: s3.region.amazonaws.com/bucket/key
    if host.startswith("s3.") and path.startswith(f"{S3_BUCKET}/"):
        return path[len(S3_BUCKET) + 1 :] or None

    # pattern 3: custom endpoint (minio): endpoint/bucket/key
    if S3_ENDPOINT and host in S3_ENDPOINT:
        if path.startswith(f"{S3_BUCKET}/"):
            return path[len(S3_BUCKET) + 1 :] or None

    # last resort: если явно видно /<bucket>/<key>
    if path.startswith(f"{S3_BUCKET}/"):
        return path[len(S3_BUCKET) + 1 :] or None

    return None

## removed earlier ensure_presigned_download variant (we keep unified version below)

# --- S3: upload mask helper ---
def put_mask_to_s3(key: str, data: bytes) -> str:
    s3_client().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=data,
        ContentType="image/png",
    )
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"

def s3_public_url(key: str) -> str:
    # Region-aware virtual hosted URL (improves DNS reliability in some sandboxes)
    if S3_REGION and S3_REGION not in ("us-east-1", ""):
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
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

def ensure_presigned_download(url: Optional[str] = None, key: Optional[str] = None) -> str:
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
        # boto will already choose region; URL host will include region automatically for non us-east-1
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
    """Detect face using YOLO if available, fallback to Haar, then enlarge to approximate full head.
    Strategy:
      - Run YOLO face detector (single largest face)
      - If unavailable / no detections -> Haar cascade
      - Expand box: widen by expand_ratio * W, then extend upward an additional 40% of box height
        and downward 20% to include hair + neck region.
    """
    H, W = image_bgr.shape[:2]
    mask = np.zeros((H, W), dtype=np.uint8)
    face_boxes: list[tuple[int,int,int,int]] = []

    model = _get_yolo_face_model()
    if model is not None:
        try:
            # YOLO expects RGB
            import math
            results = model.predict(image_bgr[..., ::-1], verbose=False)
            for r in results:
                boxes = r.boxes.xyxy.cpu().numpy() if getattr(r, 'boxes', None) else []
                for b in boxes:
                    x1, y1, x2, y2 = b[:4]
                    w = int(x2 - x1)
                    h = int(y2 - y1)
                    x = int(x1)
                    y = int(y1)
                    if w > 20 and h > 20:
                        face_boxes.append((x, y, w, h))
            # keep largest
            if face_boxes:
                face_boxes.sort(key=lambda b: b[2]*b[3], reverse=True)
                face_boxes = [face_boxes[0]]
        except Exception as e:
            print(f"[worker] YOLO face inference failed: {e}")

    if not face_boxes:
        # fallback Haar
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64))
        for (x, y, w, h) in faces:
            face_boxes.append((int(x), int(y), int(w), int(h)))
        if not face_boxes:
            # heuristic center fallback
            w = int(W * 0.22)
            h = int(H * 0.32)
            x = W // 2 - w // 2
            y = H // 4
            face_boxes = [(x, y, w, h)]

    for (x, y, w, h) in face_boxes:
        expand_px = int(W * expand_ratio)
        x, y, w, h = _expand_rect(x, y, w, h, expand_px, W, H)
        # head extension: extend upward 40% of box height, downward 20%
        up_extra = int(h * 0.40)
        down_extra = int(h * 0.20)
        new_y = max(0, y - up_extra)
        new_h = min(H - new_y, h + up_extra + down_extra)
        mask[new_y:new_y + new_h, x:x + w] = 255

    return mask


# ======== Head segmentation via Replicate (optional) ========
def replicate_segment_head(image_url: str, width: int, height: int) -> Optional[np.ndarray]:
    """Пытаемся получить маску головы через сегментационную модель.
    Возвращает np.ndarray (H,W) uint8 (0/255) или None при неудаче.
    """
    if not HEAD_SEGMENT_MODEL_VERSION:
        print("[worker] head-seg skip: HEAD_SEGMENT_MODEL_VERSION not set")
        return None
    try:
        print(f"[worker] head-seg start version={HEAD_SEGMENT_MODEL_VERSION} url={image_url[:80]}")
        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "version": HEAD_SEGMENT_MODEL_VERSION,
            "input": {
                "image": image_url,
                "text_prompt": HEAD_SEGMENT_TEXT_PROMPT,
            },
        }
        r = httpx.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=90)
        if r.status_code >= 400:
            print(f"[worker] head-seg create error {r.status_code}: {r.text[:300]}")
            return None
        data = r.json()
        get_url = (data.get("urls") or {}).get("get")
        if not get_url:
            print("[worker] head-seg error: missing get url in response")
            return None
        pred_id = data.get("id")
        if pred_id:
            print(f"[worker] head-seg prediction id={pred_id}")
        # poll (reuse replicate_poll but без вебхуков)
        seg_final = replicate_poll(get_url, max_wait_sec=180, step_sec=2.0)
        if seg_final.get("status") != "succeeded":
            print(f"[worker] head-seg status={seg_final.get('status')} detail={seg_final}")
            return None
        out_url = seg_final.get("output")
        if not out_url:
            print("[worker] head-seg error: no output url")
            return None
        if isinstance(out_url, list):  # на случай если список
            out_url = out_url[0] if out_url else None
        if not out_url:
            return None
        # качаем изображение сегментации
        img_bytes = http_get_bytes(out_url, timeout=60)
        try:
            seg_img = Image.open(io.BytesIO(img_bytes))
        except Exception:
            return None
        # приводим к размерам исходного кадра
        if seg_img.size != (width, height):
            seg_img = seg_img.resize((width, height))
        # генерируем бинарную маску: если есть альфа — берём её, иначе threshold по уровню серого
        if seg_img.mode in ("RGBA", "LA"):
            alpha = seg_img.split()[-1]
            mask_arr = np.array(alpha)
        else:
            gray = seg_img.convert("L")
            mask_arr = np.array(gray)
        # threshold: всё >16 -> 255
        mask_bin = (mask_arr > 16).astype(np.uint8) * 255
        # легкое расширение области вверх/вниз как и в make_face_mask (эмуляция)
        # возьмём bbox ненулевых
        ys, xs = np.where(mask_bin > 0)
        if ys.size and xs.size:
            y1, y2 = ys.min(), ys.max()
            x1, x2 = xs.min(), xs.max()
            h = y2 - y1 + 1
            up_extra = int(h * 0.25)
            down_extra = int(h * 0.15)
            y1 = max(0, y1 - up_extra)
            y2 = min(height - 1, y2 + down_extra)
            mask_bin[y1:y2+1, x1:x2+1] = 255
        return mask_bin
    except Exception as e:
        print(f"[worker] head-seg exception: {e}")
        return None


# ======== Replicate ========
def replicate_create_prediction(version: str, input_payload: Dict[str, Any], *, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
    """Create prediction on Replicate with provided model version and inputs."""
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    payload = {
        "version": version,
        "input": input_payload,
        # webhook optional: оставляем, если публичная ручка будет реализована
        "webhook": f"{API_BASE_URL}/api/webhooks/replicate",
        # Replicate валидирует список; допустимы: start, output, logs, completed
        "webhook_events_filter": ["start", "output", "completed"],
    }
    r = httpx.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=90)
    if r.status_code >= 400:
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
def fetch_source_image_bgr(original_url: str, original_key: Optional[str]):
    # ... пытаемся сходить по original_url ...
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(original_url)
            if resp.status_code == 200:
                img_bytes = resp.content
                source_image_url = original_url
                # decode to BGR
                img_array = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)  # BGR
                return img, source_image_url
            else:
                # 403 и т.п. — идём за presigned
                pass
    except Exception:
        pass

    # fallback: presign по key
    if original_key:
        presigned = ensure_presigned_download(key=original_key)
    else:
        # пробуем достать ключ из URL и подписать
        extracted = _extract_key_from_s3_url(original_url)
        if not extracted:
            raise RuntimeError("Cannot fetch image: neither original_key provided nor extractable from URL")
        presigned = ensure_presigned_download(key=extracted)

    # теперь качаем уже presigned
    with httpx.Client(timeout=60.0) as client:
        r = client.get(presigned)
        r.raise_for_status()
        img_bytes = r.content

    img_array = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return img, presigned

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

# --- Backwards-compat shims (старые имена, чтобы не падало) ---
def _download(url: str) -> np.ndarray:
    # прежние места вызова будут работать; но лучше см. правку №2 ниже
    return http_get_image_bgr(url)

def _to_png_bytes(arr: np.ndarray) -> bytes:
    # эквивалент прежней функции
    pil = Image.fromarray(arr)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()

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

    # 2) Маска: стратегия — face -> pose -> (optional segmentation/person based on flags) -> person -> center
    existing_mask_key = info.get("mask_key")
    overwrite = os.environ.get("HEAD_MASK_OVERWRITE", "0") == "1"
    if existing_mask_key and not overwrite:
        mask_key = existing_mask_key
        print(f"[worker] frame {frame_id}: reuse existing mask {mask_key}")
        mask_url = s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": mask_key},
            ExpiresIn=3600,
        )
    else:
        # скачиваем оригинал локально для head mask (используем presigned для приватного)
        presigned_original = ensure_presigned_download(original_url, original_key)
        img_bytes = http_get_bytes(presigned_original, timeout=120)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_in:
            tmp_in.write(img_bytes)
            tmp_in_path = tmp_in.name
        # Provide presigned original URL to segmentation fallback so Replicate can fetch image
        force_seg = (info.get("pending_params") or {}).get("force_segmentation_mask") is True
        # Для форсированной сегментации: временно ставим переменную окружения HEAD_SEGMENT_BEFORE_PERSON=1
        old_before = os.environ.get("HEAD_SEGMENT_BEFORE_PERSON")
        if force_seg:
            os.environ["HEAD_SEGMENT_BEFORE_PERSON"] = "1"
        try:
            meta, mask_path = generate_head_mask_auto(tmp_in_path, "/tmp/head_mask.png", ensure_presigned_download(original_url, original_key))
        finally:
            if force_seg:
                if old_before is None:
                    os.environ.pop("HEAD_SEGMENT_BEFORE_PERSON", None)
                else:
                    os.environ["HEAD_SEGMENT_BEFORE_PERSON"] = old_before
        # загрузка маски в S3 (унифицированный ключ)
        mask_key = f"masks/{sku_code}/{frame_id}.png"
        with open(mask_path, "rb") as f:
            put_mask_to_s3(mask_key, f.read())
        # регистрация mask_key + meta в API (без вызова /redo чтобы не запускать лишнюю генерацию)
        try:
            payload = {"key": mask_key}
            if isinstance(meta, dict):
                if meta.get("strategy"):
                    payload["strategy"] = meta.get("strategy")
                if meta.get("box"):
                    payload["box"] = list(meta.get("box")) if not isinstance(meta.get("box"), list) else meta.get("box")
            with httpx.Client(timeout=30) as c:
                c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/mask", json=payload)
        except Exception as e:
            print(f"[worker] failed to register mask key frame={frame_id}: {e}")
        print(f"[worker] frame {frame_id}: auto mask strategy={meta.get('strategy')} box={meta.get('box')}")
        # безопасный URL для Replicate (presign)
        mask_url = s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": mask_key},
            ExpiresIn=3600,
        )

    image_url_for_model = ensure_presigned_download(original_url, original_key)
    mask_url_for_model  = ensure_presigned_download(None, mask_key)

    # 3) промпт (дефолтная "Маша" если профиля нет)
    head = info.get("head") or {}
    token = head.get("trigger_token") or head.get("trigger") or "tnkfwm1"
    tmpl = head.get("prompt_template") or head.get("prompt") or "a photo of {token} female model"
    prompt = str(tmpl).replace("{token}", token)

    # 4) регистрируем генерацию в бэке
    with httpx.Client(timeout=60) as c:
        reg = c.post(f"{API_BASE_URL}/internal/frame/{frame_id}/generation", json={})
        reg.raise_for_status()
        reg_json = reg.json()
    generation_id = reg_json.get("id")
    if not generation_id:
        raise RuntimeError("internal generation create returned no id")

    source_image_url = original_url
    if original_key:  # всегда безопаснее давать presigned в Replicate
        source_image_url = s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": original_key},
            ExpiresIn=3600,
        )

    # 5) делаем prediction на Replicate
    model_version = head.get("model_version") or os.getenv("REPLICATE_MODEL_VERSION") or os.getenv("REPLICATE_MODEL")
    if not model_version:
        raise RuntimeError("No model_version available (head.model_version or REPLICATE_MODEL_VERSION env)")
    # пользовательские pending_params (internal.redo сохранил их в pending_params frame)
    pending = info.get("pending_params") or {}
    # Defaults from head.params (if provided) now merged before applying pending overrides
    head_params = head.get("params") or {}
    def _p(name, fallback):
        if name in pending:  # explicit user override (redo)
            return pending[name]
        if name in head_params:  # per-head default
            return head_params[name]
        return fallback
    input_dict = {
        "prompt": pending.get("prompt", prompt),
        "prompt_strength": _p("prompt_strength", 0.8),
        "num_outputs": _p("num_outputs", 3),
    "num_inference_steps": _p("num_inference_steps", 50),  # updated global default 50
    "guidance_scale": _p("guidance_scale", 2),
        "output_format": _p("output_format", "png"),
        "image": image_url_for_model,
        "mask": mask_url_for_model,
    }
    try:
        print(f"[worker] frame {frame_id}: pending_params={pending} head_params={head_params} final_input={input_dict}")
    except Exception:
        pass

    try:
        pred = replicate_create_prediction(model_version, input_dict, idempotency_key=f"gen-{generation_id}")
    except Exception as e:
        print(f"[worker] replicate create failed frame={frame_id} gen={generation_id}: {e}")
        return
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
    # уведомляем API о завершении генерации
    try:
        with httpx.Client(timeout=60) as c:
            c.post(
                f"{API_BASE_URL}/internal/generation/{generation_id}/complete",
                json={"outputs": outputs},
            )
    except Exception as e:
        print(f"[worker] failed to notify completion gen={generation_id}: {e}")
