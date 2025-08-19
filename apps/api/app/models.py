from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum, JSON, func, UniqueConstraint
from datetime import datetime
import enum

class Base(DeclarativeBase): pass

class FrameStatus(str, enum.Enum):
    NEW = "NEW"
    MASKED = "MASKED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"

class GenStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class HeadProfile(Base):
    __tablename__ = "head_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    replicate_model: Mapped[str] = mapped_column(String(255))  # owner/model:version
    trigger_token: Mapped[str] = mapped_column(String(64))     # напр. "tnkfwm1"
    prompt_template: Mapped[str] = mapped_column(String(512), default="a photo of {token} female model")
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # хранение дефолтных параметров head
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class SKU(Base):
    __tablename__ = "skus"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=False, index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    head_profile_id: Mapped[int | None] = mapped_column(ForeignKey("head_profiles.id"), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    head: Mapped["HeadProfile"] = relationship()
    frames: Mapped[list["Frame"]] = relationship(back_populates="sku")

class Frame(Base):
    __tablename__ = "frames"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    original_key: Mapped[str] = mapped_column(String(512))
    mask_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[FrameStatus] = mapped_column(Enum(FrameStatus), default=FrameStatus.NEW)
    pending_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    sku: Mapped["SKU"] = relationship(back_populates="frames")
    generations: Mapped[list["Generation"]] = relationship(back_populates="frame")
    output_versions: Mapped[list["FrameOutputVersion"]] = relationship(back_populates="frame")
    favorites: Mapped[list["FrameFavorite"]] = relationship(back_populates="frame")

class Generation(Base):
    __tablename__ = "generations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    frame_id: Mapped[int] = mapped_column(ForeignKey("frames.id"))
    status: Mapped[GenStatus] = mapped_column(Enum(GenStatus), default=GenStatus.PENDING)
    replicate_prediction_id: Mapped[str | None] = mapped_column(String(128))
    output_keys: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    frame: Mapped["Frame"] = relationship(back_populates="generations")


class FrameOutputVersion(Base):
    __tablename__ = "frame_output_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    frame_id: Mapped[int] = mapped_column(ForeignKey("frames.id"), index=True)
    version_index: Mapped[int] = mapped_column(Integer)  # начинается с 1
    keys: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    frame: Mapped["Frame"] = relationship(back_populates="output_versions")
    __table_args__ = (UniqueConstraint("frame_id", "version_index"),)


class FrameFavorite(Base):
    __tablename__ = "frame_favorites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    frame_id: Mapped[int] = mapped_column(ForeignKey("frames.id"), index=True)
    key: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    frame: Mapped["Frame"] = relationship(back_populates="favorites")
    __table_args__ = (UniqueConstraint("frame_id", "key"),)
