import os
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
import boto3
from datetime import datetime
from ..store import SKU_FRAMES

# In-memory store из app/store.py
# Предпочитаем реальные функции, если они есть в store.py
try:
    from ..store import list_frames_for_sku, get_frame
except Exception:
    # Фоллбек: берём сырые структуры и даём минимальные реализации
    from ..store import FRAMES, SKU_FRAMES
    from typing import Any, List

    def _int_from(val: Any, prefix: str) -> int:
        s = str(val)
        if s.startswith(prefix + "_"):
            s = s.split("_", 1)[1]
        if s.isdigit():
            return int(s)
        # не поднимаем здесь HTTPException — оставим совместимость с твоей логикой
        raise ValueError(f"Bad id format: {val!r}")

    def list_frames_for_sku(sku_id: int) -> List[dict]:
        ids = SKU_FRAMES.get(int(sku_id), [])
        return [FRAMES[i] for i in ids if i in FRAMES]

    def get_frame(frame_id: Any):
        try:
            fid = _int_from(frame_id, "fr")
        except Exception:
            fid = int(frame_id)  # вдруг уже int
        return FRAMES.get(fid)

# Поколения (генерации)
try:
    from ..store import GENERATIONS, next_generation_id  # type: ignore
except Exception:
    GENERATIONS: Dict[int, Dict[str, Any]] = {}
    def next_generation_id() -> int:
        return (max(GENERATIONS.keys()) + 1) if GENERATIONS else 1

router = APIRouter(prefix="/internal", tags=["internal"])

S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=AWS_KEY or None,
        aws_secret_access_key=AWS_SECRET or None,
    )

def _public_url(key: str) -> str:
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"

def _signed_get_url(key: str, expires_seconds: int = 3600) -> str:
    return _s3().generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires_seconds,
    )

def _frame_view(fr: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "id": fr["id"],
        "sku": fr["sku"],
        "head": fr.get("head"),
        "original_key": fr.get("original_key"),
        "original_url": fr.get("original_url"),
        "mask_key": fr.get("mask_key"),
        "mask_url": fr.get("mask_url"),
        "variants": fr.get("variants", []),
        "generations": fr.get("generations", []),
    }
    if not out.get("original_url") and out.get("original_key"):
        out["original_url"] = _signed_get_url(out["original_key"])
    if not out.get("mask_url") and out.get("mask_key"):
        out["mask_url"] = _public_url(out["mask_key"])
    return out

from fastapi import HTTPException  # убедись, что импорт есть сверху файла

def _sku_to_int(sku_id_any) -> int:
    """
    Принимает 1, "1" или "sku_1" и возвращает 1.
    Иначе бросает 422.
    """
    # уже int
    if isinstance(sku_id_any, int):
        return sku_id_any
    # строка вида "sku_1" или "1"
    s = str(sku_id_any)
    if s.startswith("sku_"):
        s = s.split("_", 1)[1]
    if s.isdigit():
        return int(s)
    raise HTTPException(status_code=422, detail="Invalid sku id format")

@router.get("/sku/{sku_id}/frames")
def internal_sku_frames(sku_id: str):
    """
    Возвращает список кадров для SKU.
    Поддерживает идентификаторы вида '1' и 'sku_1'.
    Формат ответа: {"frames": [{"id": <int>}, ...]}
    """
    # нормализуем id
    try:
        sid = int(str(sku_id).split("_")[-1])   # "sku_1" -> 1
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad sku_id")

    ids = list(SKU_FRAMES.get(sid, []))  # если у вас есть list_frames_for_sku(sid), можно вызвать его
    return {"frames": [{"id": fid} for fid in ids]}

@router.get("/frame/{frame_id}")
def internal_frame_info(frame_id: str | int):
    fr = get_frame(frame_id)
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")

    resp = {
        "id": fr["id"],
        "sku": fr["sku"],
        "original_key": fr.get("original_key"),
        "head": fr.get("head"),
        # если у тебя уже есть поле с генерациями — отдаём аккуратно
        "generations": fr.get("generations", []),
    }
    # original_url делаем НЕобязательным — если есть, отдадим, если нет, воркер сам сделает presigned GET по original_key
    if fr.get("original_url"):
        resp["original_url"] = fr["original_url"]

    return resp

@router.post("/frame/{frame_id}/generation")
def internal_register_generation(frame_id: int):
    fr = FRAMES.get(frame_id)
    if not fr:
        raise HTTPException(404, "Frame not found")
    gid = next_generation_id()
    GEN = {
        "id": gid,
        "frame_id": frame_id,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "prediction_id": None,
        "output": [],
    }
    GENERATIONS[gid] = GEN
    fr.setdefault("generations", []).append(gid)
    return {"id": gid}

@router.post("/generation/{gen_id}/prediction")
def internal_attach_prediction(gen_id: int, body: Dict[str, Any]):
    gen = GENERATIONS.get(gen_id)
    if not gen:
        raise HTTPException(404, "Generation not found")
    pred_id = body.get("prediction_id")
    if not pred_id:
        raise HTTPException(400, "prediction_id is required")
    gen["prediction_id"] = pred_id
    gen["status"] = "running"
    return {"ok": True}

@router.post("/generation/{gen_id}/result")
def internal_attach_result(gen_id: int, body: Dict[str, Any]):
    gen = GENERATIONS.get(gen_id)
    if not gen:
        raise HTTPException(404, "Generation not found")
    urls = body.get("urls") or body.get("output") or []
    if not isinstance(urls, list):
        raise HTTPException(400, "urls must be a list")
    gen["output"] = urls
    gen["status"] = "succeeded"
    fr = FRAMES.get(gen["frame_id"])
    if fr is not None:
        fr.setdefault("variants", [])
        for u in urls:
            if u not in fr["variants"]:
                fr["variants"].append(u)
    return {"ok": True, "saved": len(urls)}

@router.post("/generation/{gen_id}/status")
def internal_update_status(gen_id: int, body: Dict[str, Any]):
    gen = GENERATIONS.get(gen_id)
    if not gen:
        raise HTTPException(404, "Generation not found")
    status = body.get("status")
    if status:
        gen["status"] = status
    if body.get("error"):
        gen["error"] = body["error"]
    return {"ok": True}

# Для дашборда: отдаём состояние SKU по коду
@router.get("/sku/by-code/{sku_code}/view")
def sku_view_by_code(sku_code: str):
    sku_id = SKU_BY_CODE.get(sku_code)
    if not sku_id:
        raise HTTPException(404, "SKU not found")
    fids = SKU_FRAMES.get(sku_id, [])
    frames = [_frame_view(FRAMES[fid]) for fid in fids if fid in FRAMES]
    total = len(frames)
    done = sum(1 for fr in frames if fr.get("variants"))
    return {
        "sku": {"code": sku_code, "id": sku_id},
        "total": total,
        "done": done,
        "frames": frames,
    }
