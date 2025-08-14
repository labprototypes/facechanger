from fastapi import APIRouter, HTTPException
from ..database import db_session
from ..models import HeadProfile
from ..schemas import HeadCreate, HeadOut

router = APIRouter()

@router.post("/", response_model=HeadOut)
def create_head(body: HeadCreate):
    db = db_session()
    existing = db.query(HeadProfile).filter(HeadProfile.name == body.name).first()
    if existing: return existing
    hp = HeadProfile(
        name=body.name,
        replicate_model=body.replicate_model,
        trigger_token=body.trigger_token,
        prompt_template=body.prompt_template,
    )
    db.add(hp); db.commit(); db.refresh(hp)
    return hp

@router.get("/", response_model=list[HeadOut])
def list_heads():
    db = db_session()
    return db.query(HeadProfile).order_by(HeadProfile.id.desc()).all()
