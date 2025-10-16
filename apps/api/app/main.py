from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes.skus import router as skus_router
from .routes.heads import router as heads_router
from .routes.internal import router as internal_router
from .routes.dashboard import router as dashboard_router
from .routes.webhooks import router as webhooks_router
from .store import HEADS, create_head
from .database import init_db, get_session
from . import models


app = FastAPI()

# CORS можно сузить позже
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True}

@app.get("/health")
def health():
    return {"status": "ok"}

# публичные ручки
app.include_router(skus_router, prefix="/api")
app.include_router(heads_router, prefix="/api")
app.include_router(dashboard_router)
app.include_router(webhooks_router, prefix="/api")

# служебные ручки для воркера (мы уже указываем полный префикс внутри файла)
app.include_router(internal_router)

# Seed predefined heads (cleaned & updated)
DEFAULT_HEAD_PARAMS = {
    "prompt_strength": 0.9,
    "num_inference_steps": 50,
    "guidance_scale": 2,
    "num_outputs": 3,
    "output_format": "png",
}

PREDEFINED_HEADS = [
    # New order with new heads first
    {"name": "James2", "trigger": "smjames2", "model_version": "labprototypes/smjames2:594c1c3d946f67c75a09c27a70312d7ef0085f58967187a787ab08a52d4c4f2e", "params": DEFAULT_HEAD_PARAMS, "prompt_template": "a photo of {token} male model"},
    {"name": "Rob2",   "trigger": "smrob2",   "model_version": "labprototypes/smrob2:ce78c962565bfaad1f8471d3013b5961cb5319df5d9ac61d737a3cd4e685d884", "params": DEFAULT_HEAD_PARAMS, "prompt_template": "a photo of {token} male model"},
    {"name": "Ann2",   "trigger": "smann2",   "model_version": "labprototypes/smann2:cdae6b924f139956bb941aaee8afcd3d505f1c02c013de7b696650d7736c4a60", "params": DEFAULT_HEAD_PARAMS, "prompt_template": "a photo of {token} female model"},
    {"name": "Kate2",  "trigger": "smkate2",  "model_version": "labprototypes/smkate2:edfb83c9442d75bdcd8846bd88d0a03ed31cdcaad3a0fda79b6a4cb57b8d8fca", "params": DEFAULT_HEAD_PARAMS, "prompt_template": "a photo of {token} female model"},
    {"name": "Jack",   "trigger": "smjack",   "model_version": "labprototypes/smjack:7435b4e8f68c48bedda1dcd24d1a90647812b548f1e8e86597fbc820bfe23858", "params": DEFAULT_HEAD_PARAMS, "prompt_template": "a photo of {token} boy model"},
    {"name": "Julie",  "trigger": "smjulie",  "model_version": "labprototypes/smjulie:f75df25f746e74b4bdc49132315aacb605922d8a5894b7057d81f53f3c256f1e", "params": DEFAULT_HEAD_PARAMS, "prompt_template": "a photo of {token} girl model"},
]

def _seed_heads():
    # map trigger -> head record
    trigger_index = {h.get("trigger"): h for h in HEADS.values()}
    for h in PREDEFINED_HEADS:
        trig = h["trigger"]
        if trig not in trigger_index:
            # create new head
            create_head({
                "name": h["name"],
                "trigger": trig,
                "model_version": h["model_version"],
                "params": dict(h.get("params") or {}),
                "prompt_template": h.get("prompt_template"),
            })
        else:
            # update existing params with any newly introduced defaults; force num_inference_steps update
            rec = trigger_index[trig]
            params = rec.setdefault("params", {})
            for k, v in h.get("params", {}).items():
                if k == "num_inference_steps":
                    params[k] = v  # force override to new default 50
                else:
                    params.setdefault(k, v)

try:
    init_db()
except Exception as e:
    print(f"[startup] DB init failed: {e}")

# ---------------------------------------------------------------------------
# Fallback schema patching: ensure new columns exist if migrations not applied
# ---------------------------------------------------------------------------
def _ensure_schema_patches():
    """Best-effort creation of columns that recent code expects.
    This prevents runtime 500s if Alembic migration wasn't run yet."""
    from sqlalchemy import text
    try:
        sess = get_session()
    except Exception as e:
        print(f"[startup] cannot get session for schema patch: {e}")
        return
    try:
        # skus.is_done
        try:
            sess.execute(text("ALTER TABLE skus ADD COLUMN IF NOT EXISTS is_done BOOLEAN DEFAULT FALSE"))
            sess.commit()
            try:
                sess.execute(text("ALTER TABLE skus ALTER COLUMN is_done DROP DEFAULT"))
                sess.commit()
            except Exception:
                sess.rollback()
        except Exception as e:
            sess.rollback(); print(f"[startup] schema patch (is_done) skipped: {e}")
        # frames.accepted
        try:
            sess.execute(text("ALTER TABLE frames ADD COLUMN IF NOT EXISTS accepted BOOLEAN DEFAULT FALSE"))
            sess.commit()
            try:
                sess.execute(text("ALTER TABLE frames ALTER COLUMN accepted DROP DEFAULT"))
                sess.commit()
            except Exception:
                sess.rollback()
        except Exception as e:
            sess.rollback(); print(f"[startup] schema patch (accepted) skipped: {e}")
    finally:
        sess.close()

_ensure_schema_patches()

def _seed_heads_db():
    from sqlalchemy import select
    from sqlalchemy.exc import ProgrammingError, OperationalError
    sess = get_session()
    try:
        try:
            existing = {h.trigger_token: h for h in sess.execute(select(models.HeadProfile)).scalars().all()}
        except (ProgrammingError, OperationalError) as e:
            # Likely tables not created yet (e.g. before migrations applied). Avoid crashing startup.
            print(f"[startup] skip DB head seeding (tables missing?): {e}")
            sess.rollback()
            return
        for h in PREDEFINED_HEADS:
            trig = h["trigger"]
            if trig in existing:
                # update params if missing fields / force num_inference_steps update
                hp = existing[trig]
                params = hp.params or {}
                changed = False
                for k, v in h["params"].items():
                    if k not in params or (k == "num_inference_steps" and params.get(k) != v):
                        params[k] = v
                        changed = True
                if changed:
                    hp.params = params
                    sess.add(hp)
            else:
                sess.add(models.HeadProfile(
                    name=h["name"],
                    replicate_model=h["model_version"],
                    trigger_token=trig,
                    prompt_template=h.get("prompt_template") or "a photo of {token} female model",
                    params=h["params"],
                ))
        sess.commit()
    finally:
        sess.close()

_seed_heads()  # legacy in-memory (можно убрать позже)
_seed_heads_db()
