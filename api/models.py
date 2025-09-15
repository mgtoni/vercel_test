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

