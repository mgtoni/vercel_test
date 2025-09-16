from pydantic import BaseModel
from typing import Optional


class FormData(BaseModel):
    name: str
    email: str


class AuthData(BaseModel):
    mode: str  # 'login' or 'signup'
    # Plain fields (backwards compatibility); avoided when `enc` provided
    email: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    # Encrypted compact payload (base64-encoded RSA-OAEP)
    enc: Optional[str] = None


class ProfileReq(BaseModel):
    rtk: str  # base64 AES key from client


# Admin: pdf_assets manifest models
class PdfAssetBase(BaseModel):
    group_key: str
    bucket: str
    path: str
    label: Optional[str] = None
    order_index: Optional[int] = 0
    is_default: Optional[bool] = False
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    active: Optional[bool] = True


class PdfAssetCreate(PdfAssetBase):
    pass


class PdfAssetUpdate(BaseModel):
    group_key: Optional[str] = None
    bucket: Optional[str] = None
    path: Optional[str] = None
    label: Optional[str] = None
    order_index: Optional[int] = None
    is_default: Optional[bool] = None
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    active: Optional[bool] = None
