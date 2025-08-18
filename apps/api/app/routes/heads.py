from fastapi import APIRouter
from ..store import HEADS, create_head

router = APIRouter()

@router.get("/api/heads")
def list_heads():
    return list(HEADS.values())

@router.post("/api/heads")
def add_head(head: dict):
    return create_head(head)
