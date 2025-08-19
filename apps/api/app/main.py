from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes.skus import router as skus_router
from .routes.heads import router as heads_router
from .routes.internal import router as internal_router
from .routes.dashboard import router as dashboard_router
from .store import HEADS, create_head


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

# служебные ручки для воркера (мы уже указываем полный префикс внутри файла)
app.include_router(internal_router)

# Seed predefined heads if not already created
DEFAULT_HEAD_PARAMS = {
    "prompt_strength": 0.8,
    "num_inference_steps": 50,  # updated from 28 -> 50
    "guidance_scale": 2,
    "num_outputs": 3,
    "output_format": "png",
}

PREDEFINED_HEADS = [
    {"name": "Anna",  "trigger": "smanna",  "model_version": "labprototypes/smanna:73184591dd196bc5656fc1901c8872093a5f48fe8ffa20ff9677213519d911a8", "params": DEFAULT_HEAD_PARAMS},
    {"name": "Kate",  "trigger": "smkate",  "model_version": "labprototypes/smkate:5a2ee00ca522c7eee9645ce4a518eb95e04979d35c8099e2efefcdf487ea2ee9", "params": DEFAULT_HEAD_PARAMS},
    {"name": "James", "trigger": "smjames", "model_version": "labprototypes/smjames:c8dd353a4ddfa54dfe1788f80f6c1c39dc3db2f7bc23f680eda23a4a389c26db", "params": DEFAULT_HEAD_PARAMS},
    {"name": "Rob",   "trigger": "smrob",   "model_version": "labprototypes/smrob:d51c0d9bba5a719941e05ca816d9630445b3ae34dc723267b9081fbb98dc4776", "params": DEFAULT_HEAD_PARAMS},
    {"name": "Jack",  "trigger": "smjack",  "model_version": "labprototypes/smjack:7435b4e8f68c48bedda1dcd24d1a90647812b548f1e8e86597fbc820bfe23858", "params": DEFAULT_HEAD_PARAMS},
    {"name": "Julie", "trigger": "smjulie", "model_version": "labprototypes/smjulie:f75df25f746e74b4bdc49132315aacb605922d8a5894b7057d81f53f3c256f1e", "params": DEFAULT_HEAD_PARAMS},
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

_seed_heads()
