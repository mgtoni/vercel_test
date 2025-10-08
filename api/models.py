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
    module: str
    lesson: Optional[str] = None
    path: str
    is_default: Optional[bool] = False
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    active: Optional[bool] = True


class PdfAssetCreate(PdfAssetBase):
    pass


class PdfAssetUpdate(BaseModel):
    module: Optional[str] = None
    lesson: Optional[str] = None
    path: Optional[str] = None
    is_default: Optional[bool] = None
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    active: Optional[bool] = None


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminPasswordResetRequest(BaseModel):
    reset_token: str
    new_password: str

