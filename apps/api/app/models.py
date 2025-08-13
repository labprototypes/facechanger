from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, JSON
from datetime import datetime
from .database import Base

class Batch(Base):
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True)
    date = Column(String, index=True)

class HeadProfile(Base):
    __tablename__ = "head_profiles"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    trigger_token = Column(String)
    replicate_model = Column(String)
    params = Column(JSON)
    negative_prompt = Column(String)
    seed_bank = Column(JSON)
    seed_policy = Column(String)

class SKU(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    sku_code = Column(String, unique=True, index=True)
    head_profile_id = Column(Integer, ForeignKey("head_profiles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Frame(Base):
    __tablename__ = "frames"
    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey("skus.id"))
    filename = Column(String)
    raw_url = Column(String)
    mask_url = Column(String, nullable=True)
    mask_auto = Column(Boolean, default=True)
    current_version = Column(Integer, default=0)

class Version(Base):
    __tablename__ = "versions"
    id = Column(Integer, primary_key=True)
    frame_id = Column(Integer, ForeignKey("frames.id"))
    n = Column(Integer)
    prompt = Column(String)
    params = Column(JSON)
    status = Column(String, index=True)

class Output(Base):
    __tablename__ = "outputs"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("versions.id"))
    idx = Column(Integer)
    result_url = Column(String)
    thumb_url = Column(String)
    pinned = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)
    qc = Column(JSON)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
