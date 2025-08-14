from pydantic import BaseModel
from typing import List, Optional

class HeadCreate(BaseModel):
    name: str
    replicate_model: str  # owner/model:version
    trigger_token: str
    prompt_template: str = "a photo of {token} female model"

class HeadOut(BaseModel):
    id: int
    name: str
    class Config: from_attributes = True

class UploadFileReq(BaseModel):
    filename: str
    size: int

class UploadUrlsReq(BaseModel):
    files: List[UploadFileReq]

class RegisterItem(BaseModel):
    filename: str
    key: str

class RegisterReq(BaseModel):
    files: List[RegisterItem]
    head_name: Optional[str] = None  # если хотим сразу проставить "Маша"
