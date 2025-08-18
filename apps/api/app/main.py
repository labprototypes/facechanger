from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes.skus import router as skus_router
from .routes.heads import router as heads_router
from .routes.internal import router as internal_router


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
app.include_router(heads_router, prefix="")

# служебные ручки для воркера (мы уже указываем полный префикс внутри файла)
app.include_router(internal_router)
