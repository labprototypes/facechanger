# apps/api/app/routes/internal.py
# -*- coding: utf-8 -*-

"""
Внутренние ручки для воркера и дашборда.

Что даёт модуль:
- GET  /internal/sku/{sku_id}/frames
- GET  /internal/frame/{frame_id}
- POST /internal/frame/{frame_id}/generation
- POST /internal/generation/{generation_id}/prediction
- GET  /internal/frame/{frame_id}/generations
- (опционально) debug presign/public ссылок на S3

Особенности:
- Поддержка формата sku_id как "1" и "sku_1"
- Гарантируем наличие original_url в ответе (через public или presigned)
- Минимальные зависимости от внутреннего устройства store: используем только функции
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import boto3
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---- store API (функции должны быть реализованы в apps/api/app/store.py) ----
from ..store import (
    list_frames_for_sku, get_frame, set_frame_status,
    register_generation, save_generation_prediction, generations_for_frame,
    set_generation_outputs, set_frame_outputs, append_frame_outputs_version,
    set_frame_favorites, get_frame_favorites, get_sku_by_code, set_frame_mask,
    get_all_sku_codes, list_sku_codes_by_date, set_frame_pending_params,
    SKU_BY_CODE, delete_frame, delete_sku
)
USE_DB = bool(os.environ.get("DATABASE_URL"))

router = APIRouter(prefix="/internal", tags=["internal"])

# ---- S3 конфиг из окружения ----
S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION")       # у тебя us-east-2
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")   # если MinIO / кастом
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")
S3_REQUIRE_SIGNED = os.environ.get("S3_REQUIRE_SIGNED", "1").lower() in ("1","true","yes","on")


# =============================================================================
# S3 helpers
# =============================================================================
def _s3_client():
    """
    Клиент S3 с поддержкой кастомного endpoint и region.
    """
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT or None,
        region_name=S3_REGION or None,
        aws_access_key_id=AWS_KEY or None,
        aws_secret_access_key=AWS_SECRET or None,
    )


def _s3_public_url(key: str) -> str:
    """Return region-aware public URL (virtual-hosted style).
    For non us-east-1 buckets some execution environments (e.g. Replicate sandboxes)
    may fail DNS resolving bucket.s3.amazonaws.com; prefer bucket.s3.<region>.amazonaws.com
    when region is known and != us-east-1."""
    if S3_REGION and S3_REGION not in ("us-east-1", ""):
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
    return f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"


def _s3_signed_get(key: str, expires: int = 3600) -> str:
    """
    Presigned GET URL (если бакет приватный) — годится и для воркера, и для UI.
    """
    cli = _s3_client()
    return cli.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )

def _best_url_for_key(key: str) -> str:
    """Return either public or presigned URL depending on config."""
    if not key:
        return ""
    if S3_REQUIRE_SIGNED:
        try:
            return _s3_signed_get(key)
        except Exception:
            # fallback to public if signing failed
            return _s3_public_url(key)
    else:
        return _s3_public_url(key)


# =============================================================================
# Модели
# =============================================================================
class PredictionIn(BaseModel):
    prediction_id: str


# =============================================================================
# Утилиты
# =============================================================================
def _parse_sku_id(sku_id_or_code: str) -> int:
    """
    Принимает '1' или 'sku_1' — возвращает int 1.
    Генерирует 422 если формат невалидный.
    """
    s = str(sku_id_or_code)
    if s.startswith("sku_"):
        s = s[4:]
    try:
        return int(s)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid sku id format")


def _frame_to_public_json(fr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Формируем JSON для ответа: добавляем original_url
    (из fr['original_url'] либо строим по 'original_key').
    Также мягко прокидываем mask и outputs если есть.
    """
    out: Dict[str, Any] = {
        "id": fr.get("id"),
        "sku": fr.get("sku") or {},
        "head": fr.get("head") or {},
        "status": fr.get("status") or "queued",
    }

    # --- original_url ---
    original_url: Optional[str] = fr.get("original_url")
    original_key: Optional[str] = fr.get("original_key")
    # важно: прокидываем original_key чтобы воркер мог подписать приватный объект без эвристик
    if original_key:
        out["original_key"] = original_key

    if original_key:
        # Перестраиваем url в соответствии с политикой (всегда подписываем если приватный)
        original_url = _best_url_for_key(original_key)

    # Если нет ни url ни key — отдаём None (не роняем 500, так UI/воркер могут показать/логировать проблему)
    out["original_url"] = original_url

    # --- mask (если есть) ---
    if "mask_key" in fr and fr["mask_key"]:
        out["mask_key"] = fr["mask_key"]
        out["mask_url"] = _best_url_for_key(fr["mask_key"])

    # --- outputs (если уже что-то сохранили) ---
    if isinstance(fr.get("outputs"), list):
        out["outputs"] = []
        for item in fr["outputs"]:
            if isinstance(item, dict):
                key = item.get("key") or item.get("url")
                if key and '://' not in key:
                    out["outputs"].append({"key": key, "url": _best_url_for_key(key)})
                else:
                    out["outputs"].append({"key": key, "url": item.get("url") or key})
            elif isinstance(item, str):
                if '://' in item:
                    out["outputs"].append({"key": item, "url": item})
                else:
                    out["outputs"].append({"key": item, "url": _best_url_for_key(item)})
            else:
                continue

    # favorites (список ключей)
    if fr.get("favorites"):
        favs = []
        for k in fr.get("favorites", []):
            favs.append({"key": k, "url": _best_url_for_key(k)})
        out["favorites"] = favs

    return out


# =============================================================================
# Ручки
# =============================================================================
@router.get("/health")
def internal_health():
    """Простая проверка живости сервиса"""
    return {"ok": True}

## Public webhook now handled in routes/webhooks.py

@router.get("/sku/by-code/{code}/view")
def internal_sku_view_by_code(code: str):
    if USE_DB:
        sku = get_sku_by_code(code)
        if not sku:
            raise HTTPException(status_code=404, detail="sku not found")
        sid = sku["id"]
    else:
        if code not in SKU_BY_CODE:
            raise HTTPException(status_code=404, detail="sku not found")
        sid = SKU_BY_CODE[code]
    frames = list_frames_for_sku(sid) or []
    items = []
    for idx, fr in enumerate(frames, start=1):
        obj = _frame_to_public_json(fr)
        obj["seq"] = idx  # local sequential number per SKU starting at 1
        # добавим версионность если есть
        if fr.get("outputs_versions"):
            obj["outputs_versions"] = []
            for vers in fr["outputs_versions"]:
                obj["outputs_versions"].append([
                    _s3_public_url(k) if not S3_REQUIRE_SIGNED else _best_url_for_key(k) for k in vers
                ])
        if fr.get("pending_params"):
            obj["pending_params"] = fr.get("pending_params")
        items.append(obj)
    return {"sku": {"id": sid, "code": code}, "frames": items}

@router.get("/internal/s3/presign-get")
def presign_get_url(key: str):
    """
    Возвращает presigned GET url для S3 key.
    """
    return {"url": _s3_signed_get(key)}

@router.get("/sku/{sku_id}/frames")
def internal_sku_frames(sku_id: str):
    """
    Вернуть список кадров для SKU. Поддерживает '1' и 'sku_1'.
    Возвращает {"frames": [ ... ]} со сведениями по каждому кадру.
    """
    sid = _parse_sku_id(sku_id)

    frames = list_frames_for_sku(sid) or []
    items: List[Dict[str, Any]] = []

    # list_frames_for_sku может вернуть список id или список dict'ов.
    if frames and isinstance(frames[0], int):
        for fid in frames:
            fr = get_frame(int(fid))
            if not fr:
                # мягко пропускаем битые ссылки
                continue
            items.append(_frame_to_public_json(fr))
    else:
        # уже пришли словари
        for fr in frames:
            if not isinstance(fr, dict):
                # если по ошибке пришёл тип, ниспадаем 500
                # а мягко игнорируем
                continue
            items.append(_frame_to_public_json(fr))

    return {"frames": items}


@router.get("/frame/{frame_id}")
def internal_frame_info(frame_id: int):
    """
    Полная информация по кадру.
    Гарантируем original_url (public или presigned) в ответе.
    """
    fr = get_frame(int(frame_id))
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")

    return _frame_to_public_json(fr)


@router.post("/frame/{frame_id}/generation")
def internal_create_generation(frame_id: int):
    """
    Зарегистрировать новую генерацию по кадру (внутренний ID).
    Возвращает {"id": <generation_id:int>}
    Также пытаемся обновить статус кадра на "generating".
    """
    fr = get_frame(int(frame_id))
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")

    gid = register_generation(int(frame_id))

    # Статус обновляем без жёстких требований (если store не поддерживает — просто пропустим)
    try:
        set_frame_status(int(frame_id), "generating")
    except Exception:
        pass

    return {"id": gid}


class _PredictionBody(BaseModel):
    prediction_id: str


class _GenerationCompleteBody(BaseModel):
    outputs: list[str] = []  # список публичных S3 URL или ключей
    status: str | None = None
    error: str | None = None

class _RedoBody(BaseModel):
    prompt: str | None = None
    prompt_strength: float | None = None
    num_inference_steps: int | None = None
    guidance_scale: float | None = None
    output_format: str | None = None
    num_outputs: int | None = None
    force_segmentation_mask: bool | None = None

class _MaskBody(BaseModel):
    key: str
    strategy: str | None = None
    box: list[int] | None = None


@router.post("/generation/{generation_id}/prediction")
def internal_set_prediction(generation_id: int, body: _PredictionBody):
    """
    Привязать prediction_id от Replicate к нашей генерации.
    """
    if not body.prediction_id:
        raise HTTPException(status_code=422, detail="prediction_id is required")

    save_generation_prediction(int(generation_id), body.prediction_id)
    return {"ok": True}


@router.post("/generation/{generation_id}/complete")
def internal_generation_complete(generation_id: int, body: _GenerationCompleteBody):
    """Worker сообщает о завершении генерации и её выходах.
    Передаём список outputs (ключи или URL)."""
    outs = body.outputs or []
    # Нормализуем public S3 URL (включая региональные) -> key
    import urllib.parse
    host_variants = {f"{S3_BUCKET}.s3.amazonaws.com"}
    if S3_REGION and S3_REGION not in ("us-east-1", ""):
        host_variants.add(f"{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com")
    norm: list[str] = []
    for o in outs:
        if isinstance(o, str) and o.startswith("http"):
            try:
                u = urllib.parse.urlparse(o)
                if u.netloc in host_variants:
                    key = u.path.lstrip('/')
                    if key:
                        norm.append(key)
                        continue
            except Exception:
                pass
        norm.append(o)
    try:
        set_generation_outputs(int(generation_id), norm)
        # Определяем frame_id корректно для обеих реализаций store.
        frame_id = None
        if USE_DB:
            # В режиме БД in-memory GENERATIONS_BY_ID пустой — достанем напрямую.
            try:
                from ..store import get_generation  # lazy import чтобы избежать циклов
                gen_rec = get_generation(int(generation_id)) or {}
                frame_id = gen_rec.get("frame_id")
            except Exception:
                frame_id = None
        else:
            # Старый путь через in-memory словарь
            from ..store import GENERATIONS_BY_ID  # type: ignore
            gen_rec = GENERATIONS_BY_ID.get(int(generation_id)) or {}
            frame_id = gen_rec.get("frame_id")

        if frame_id is not None:
            try:
                append_frame_outputs_version(int(frame_id), norm)
            except Exception:
                # Логически не критично если версия не добавилась — продолжаем.
                pass
            try:
                set_frame_status(int(frame_id), "done")
            except Exception:
                pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to set outputs: {e}")
    return {"ok": True, "count": len(norm)}


@router.get("/frame/{frame_id}/generations")
def internal_list_generations(frame_id: int):
    """
    Список генераций кадра для UI/отладки.
    Формат элементов зависит от реализации store.generations_for_frame.
    Рекомендуемый формат элемента:
    {
      "id": int,
      "prediction_id": str | None,
      "status": "queued|running|succeeded|failed",
      "outputs": [ { "key": "...", "url": "..." }, ... ]
    }
    """
    gens = generations_for_frame(int(frame_id)) or []
    # На всякий случай убедимся, что это список
    if not isinstance(gens, list):
        gens = []
    return {"items": gens}


@router.post("/frame/{frame_id}/redo")
def internal_redo_frame(frame_id: int, body: _RedoBody | None = None):
    """Пере-запустить генерацию по кадру.
    НЕ удаляем прошлые outputs (они уже в outputs_versions), просто ставим статус queued.
    Параметры из body сохраняем как pending_params чтобы воркер использовал их при следующем запуске."""
    fr = get_frame(int(frame_id))
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")
    # статус -> queued
    set_frame_status(int(frame_id), "queued")
    # сохраним параметры для воркера
    from ..store import set_frame_pending_params
    params = {}
    if body is not None:
        params = {k: v for k, v in body.dict().items() if v is not None}
    if params:
        set_frame_pending_params(int(frame_id), params)
    # enqueue
    from ..celery_client import queue_process_frame
    try:
        queue_process_frame(int(frame_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"enqueue failed: {e}")
    return {"ok": True, "frame_id": int(frame_id), "params": params}

@router.post("/frame/{frame_id}/mask")
def internal_set_mask(frame_id: int, body: _MaskBody):
    """Привязать/обновить mask_key для кадра.
    Дополнительно можно передать strategy и box (список из 4 чисел), которые будут сохранены
    в pending_params как mask_strategy / mask_box для отображения в UI без автоперезапуска.
    """
    fr = get_frame(int(frame_id))
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="key required")
    try:
        set_frame_mask(int(frame_id), key)
        meta_updates = {}
        if body.strategy:
            meta_updates["mask_strategy"] = body.strategy
        if body.box and isinstance(body.box, list):
            meta_updates["mask_box"] = body.box
        if meta_updates:
            set_frame_pending_params(int(frame_id), meta_updates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to set mask: {e}")
    return {"ok": True, "frame_id": int(frame_id), "mask_key": key, "mask_url": _best_url_for_key(key)}


@router.get("/sku/by-code/{code}/export-urls")
def internal_export_urls(code: str):
    """Вернёт плоский список всех output URL по SKU (для копирования)."""
    if USE_DB:
        sku = get_sku_by_code(code)
        if not sku:
            raise HTTPException(status_code=404, detail="sku not found")
        sid = sku["id"]
    else:
        if code not in SKU_BY_CODE:
            raise HTTPException(status_code=404, detail="sku not found")
        sid = SKU_BY_CODE[code]
    frames = list_frames_for_sku(sid) or []
    urls: list[str] = []
    for fr in frames:
        outs = fr.get("outputs") or []
        for o in outs:
            if isinstance(o, dict):
                u = o.get("url") or None
                if not u:
                    key = o.get("key")
                    if key:
                        u = _s3_public_url(key)
                if u:
                    urls.append(u)
            elif isinstance(o, str):
                # предполагаем это ключ
                if "://" in o:
                    urls.append(o)
                else:
                    urls.append(_s3_public_url(o))
    return {"sku": code, "count": len(urls), "urls": urls}


class _FavBody(BaseModel):
    keys: list[str]

@router.post("/frame/{frame_id}/favorites")
def internal_set_favorites(frame_id: int, body: _FavBody):
    fr = get_frame(int(frame_id))
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")
    set_frame_favorites(int(frame_id), body.keys)
    return {"ok": True, "favorites": get_frame_favorites(int(frame_id))}

@router.get("/frame/{frame_id}/favorites")
def internal_get_favorites(frame_id: int):
    return {"frame_id": int(frame_id), "favorites": get_frame_favorites(int(frame_id))}

@router.get("/sku/by-code/{code}/favorites.zip")
def internal_download_favorites_zip(code: str):
    from io import BytesIO
    import zipfile
    # SKU_BY_CODE already imported
    if USE_DB:
        sku = get_sku_by_code(code)
        if not sku:
            raise HTTPException(status_code=404, detail="sku not found")
        sid = sku["id"]
    else:
        if code not in SKU_BY_CODE:
            raise HTTPException(status_code=404, detail="sku not found")
        sid = SKU_BY_CODE[code]
    frames = list_frames_for_sku(sid) or []
    # collect favorite keys
    fav_items: list[tuple[str,str]] = []  # (key, arcname)
    for fr in frames:
        favs = fr.get("favorites") or []
        for k in favs:
            arcname = f"{code}/frame_{fr['id']}/{k.split('/')[-1]}"
            fav_items.append((k, arcname))
    if not fav_items:
        return {"error": "no favorites"}
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        s3c = _s3_client()
        for key, arcname in fav_items:
            try:
                obj = s3c.get_object(Bucket=S3_BUCKET, Key=key)
                data = obj['Body'].read()
                zf.writestr(arcname, data)
            except Exception:
                continue
    buf.seek(0)
    return StreamingResponse(buf, media_type='application/zip', headers={"Content-Disposition": f"attachment; filename={code}_favorites.zip"})

@router.get("/batch/{date}/export.zip")
def internal_download_batch_export(date: str):
    from io import BytesIO
    import zipfile
    # StreamingResponse imported globally
    # batch = все SKU созданные в этот date
    # Для каждого SKU включаем только избранные (если есть), иначе ничего.
    sku_codes: list[str] = []
    if USE_DB:
        sku_codes.extend(list_sku_codes_by_date(date))
    else:
        for code, sid in list(SKU_BY_CODE.items()):
            # фильтрацию по дате опускаем (in-memory store без точной привязки) — отдаём все
            sku_codes.append(code)
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        s3c = _s3_client()
        for code in sku_codes:
            if USE_DB:
                sku = get_sku_by_code(code)
                if not sku:
                    continue
                sid = sku["id"]
            else:
                sid = SKU_BY_CODE.get(code)
                if not sid:
                    continue
            frames = list_frames_for_sku(sid) or []
            any_added = False
            for fr in frames:
                favs = fr.get("favorites") or []
                for k in favs:
                    try:
                        obj = s3c.get_object(Bucket=S3_BUCKET, Key=k)
                        data = obj['Body'].read()
                        arcname = f"{code}/frame_{fr['id']}/{k.split('/')[-1]}"
                        zf.writestr(arcname, data)
                        any_added = True
                    except Exception:
                        continue
            if not any_added:
                # маркер пустого SKU
                zf.writestr(f"{code}/README.txt", "No favorites selected")
    buf.seek(0)
    return StreamingResponse(buf, media_type='application/zip', headers={"Content-Disposition": f"attachment; filename=batch_{date}.zip"})


# =============================================================================
# Отладочные ручки (можно удалить, но удобно иметь под рукой)
# =============================================================================
@router.get("/debug/s3_presign")
def debug_s3_presign(key: str, expires: int = 3600):
    """
    Вернуть presigned GET для конкретного ключа (удобно проверять доступность).
    """
    try:
        return {"url": _s3_signed_get(key, expires=expires)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/s3_public")
def debug_s3_public(key: str):
    """
    Вернуть public URL для ключа (если бакет публичный).
    """
    try:
        return {"url": _s3_public_url(key)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Deletion endpoints
# =============================================================================
@router.delete("/frame/{frame_id}")
def internal_delete_frame(frame_id: int):
    fr = get_frame(int(frame_id))
    if not fr:
        raise HTTPException(404, "frame not found")
    delete_frame(int(frame_id))
    return {"ok": True, "deleted_frame_id": int(frame_id)}

@router.delete("/sku/by-code/{code}")
def internal_delete_sku(code: str):
    if code not in SKU_BY_CODE:
        raise HTTPException(404, "sku not found")
    delete_sku(code)
    return {"ok": True, "deleted": code}
