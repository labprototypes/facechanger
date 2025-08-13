from __future__ import annotations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings
import time

class Base(DeclarativeBase):
    pass

_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        url = settings.database_url
        if not url:
            # Сделаем явную ошибку, чтобы лог был понятнее
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine

def get_session():
    """Создаёт сессию по требованию (лениво)."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal()

def init_db(max_retries: int = 15, delay_sec: float = 2.0):
    """
    Пытаемся дождаться готовности БД (на старте Render БД может ещё создаваться).
    """
    from . import models  # noqa: F401
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            eng = get_engine()
            Base.metadata.create_all(bind=eng)
            # проверочный пинг
            with eng.connect() as conn:
                conn.execute(text("select 1"))
            return
        except Exception as e:
            last_err = e
            time.sleep(delay_sec)
    # если так и не вышло — пробрасываем в лог
    raise last_err
