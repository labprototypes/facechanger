from fastapi import APIRouter, HTTPException
from ..store import HEADS, create_head

router = APIRouter()

@router.get("/heads")
def list_heads():
    return list(HEADS.values())

@router.post("/heads")
def add_head(head: dict):
    if "model_version" not in head:
        raise HTTPException(400, "model_version is required (owner/model:version_sha)")
    return create_head(head)
