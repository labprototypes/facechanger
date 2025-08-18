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
from pydantic import BaseModel

# ---- store API (функции должны быть реализованы в apps/api/app/store.py) ----
from ..store import (
    # кадры / sku
    list_frames_for_sku,         # (sku_id: int) -> List[int] | List[dict]
    get_frame,                   # (frame_id: int) -> dict | None
    set_frame_status,            # (frame_id: int, status: str) -> None
    # генерации
    register_generation,         # (frame_id: int) -> int
    save_generation_prediction,  # (generation_id: int, prediction_id: str) -> None
    generations_for_frame,       # (frame_id: int) -> List[dict]
    set_generation_outputs,      # (generation_id: int, outputs: List[str]) -> None
    set_frame_outputs,            # (frame_id: int, outputs: List[str]) -> None
)

router = APIRouter(prefix="/internal", tags=["internal"])

# ---- S3 конфиг из окружения ----
S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION")       # у тебя us-east-2
S3_ENDPOINT = os.environ.get("S3_ENDPOINT")   # если MinIO / кастом
AWS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET = os.environ.get("AWS_SECRET_ACCESS_KEY")


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
    """
    Публичный URL (если бакет публичный). Универсальный (без REGION в хосте).
    Совпадает со схемой, которую ты уже используешь в других местах проекта.
    """
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

    if not original_url and original_key:
        # Сначала попытаемся отдать public URL (короче, стабильно для UI),
        # если бакет приватный — он просто не будет работать, но UI можно научить падать на presign:
        try:
            original_url = _s3_public_url(original_key)
        except Exception:
            original_url = None

        if not original_url:
            # подстраховка — пресайн (воркеру всегда ок)
            original_url = _s3_signed_get(original_key)

    # Если нет ни url ни key — отдаём None (не роняем 500, так UI/воркер могут показать/логировать проблему)
    out["original_url"] = original_url

    # --- mask (если есть) ---
    if "mask_key" in fr and fr["mask_key"]:
        out["mask_key"] = fr["mask_key"]
        # сделаем mask_url (public), а если не пойдёт — подпишем
        try:
            out["mask_url"] = _s3_public_url(fr["mask_key"])
        except Exception:
            out["mask_url"] = _s3_signed_get(fr["mask_key"])

    # --- outputs (если уже что-то сохранили) ---
    if isinstance(fr.get("outputs"), list):
        out["outputs"] = []
        for item in fr["outputs"]:
            if isinstance(item, dict):
                # поддержка формата: {"key": "...", "url": "..."}
                out["outputs"].append(item)
            elif isinstance(item, str):
                # поддержка формата: просто ключ
                out["outputs"].append({"key": item, "url": _s3_public_url(item)})
            else:
                # неизвестный формат — мягко пропустим
                continue

    return out


# =============================================================================
# Ручки
# =============================================================================
@router.get("/health")
def internal_health():
    """Простая проверка живости сервиса"""
    return {"ok": True}

@router.post("/webhooks/replicate")
async def webhook_replicate(payload: dict, request: Request):
    """Replicate webhook stub (путь /api/webhooks/replicate)."""
    event_status = payload.get("status")
    prediction_id = payload.get("id")
    print(f"[webhook] replicate event status={event_status} id={prediction_id}")
    return {"ok": True}

@router.get("/sku/by-code/{code}/view")
def internal_sku_view_by_code(code: str):
    from ..store import SKU_BY_CODE
    if code not in SKU_BY_CODE:
        raise HTTPException(status_code=404, detail="sku not found")
    sid = SKU_BY_CODE[code]
    frames = list_frames_for_sku(sid) or []
    items = [_frame_to_public_json(fr) for fr in frames]
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
    # Нормализуем: если пришёл URL вида https://bucket.s3.amazonaws.com/key -> превращаем в key
    norm: list[str] = []
    prefix = f"https://{S3_BUCKET}.s3.amazonaws.com/"
    for o in outs:
        if o.startswith(prefix):
            norm.append(o[len(prefix):])
        else:
            norm.append(o)
    try:
        set_generation_outputs(int(generation_id), norm)
        # Продублируем на сам frame (удобно для простого UI /internal/sku/.../view)
        # Находим frame_id через GENERATIONS_BY_ID, но чтобы не тянуть его тут напрямую
        # воспользуемся generations_for_frame обходом: найдём generation и возьмём frame_id
        from ..store import GENERATIONS_BY_ID  # локальный импорт чтобы избежать циклов
        gen_rec = GENERATIONS_BY_ID.get(int(generation_id)) or {}
        frame_id = gen_rec.get("frame_id")
        if frame_id is not None:
            try:
                set_frame_outputs(int(frame_id), norm)
                # статус кадра -> done
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
def internal_redo_frame(frame_id: int):
    """Пере-запустить генерацию по кадру.
    Сбрасываем outputs и статус, ставим задачу process_frame."""
    fr = get_frame(int(frame_id))
    if not fr:
        raise HTTPException(status_code=404, detail="frame not found")
    # очистим outputs в frame и generations (мягко)
    try:
        fr.pop("outputs", None)
        set_frame_status(int(frame_id), "queued")
    except Exception:
        pass
    # (генерации не трогаем для истории)
    # enqueue
    try:
        from ..celery_client import queue_process_frame
        queue_process_frame(int(frame_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"enqueue failed: {e}")
    return {"ok": True, "frame_id": int(frame_id)}


@router.get("/sku/by-code/{code}/export-urls")
def internal_export_urls(code: str):
    """Вернёт плоский список всех output URL по SKU (для копирования)."""
    from ..store import SKU_BY_CODE
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
