import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Form, Response

from ..models import (
    AdminLoginRequest,
    AdminPasswordResetRequest,
    PdfAssetCreate,
    PdfAssetUpdate,
)
from ..utils.admin_auth import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    as_bool,
    build_password_update_payload,
    create_reset_token,
    create_session_token,
    decode_reset_payload,
    fetch_admin_user,
    hash_password,
    requires_password_change,
    update_admin_user,
    verify_password,
    verify_reset_token,
)
from ..utils.admin_checks import require_admin
from ..utils.core_supabase import build_supabase_public, create_signed_upload_url
from ..utils.crypto_utils import mask_email_for_log

router = APIRouter(prefix="/admin")
logger = logging.getLogger("api3.routes.admin")


@router.get("/me")
async def admin_me(request: Request):
    email = require_admin(request)
    return {"email": email, "is_admin": True}


@router.post("/login")
async def admin_login(body: AdminLoginRequest, response: Response):
    raw_email = (body.email or "").strip()
    password = (body.password or "").strip()
    if not raw_email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    admin_row = fetch_admin_user(raw_email)
    if not admin_row:
        logger.info(f"Admin login failed (no user): {mask_email_for_log(raw_email)}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    email = admin_row.get("email") or raw_email

    if "active" in admin_row and not as_bool(admin_row.get("active")):
        raise HTTPException(status_code=403, detail="Admin access disabled")

    stored_value = (
        admin_row.get("password_hash")
        or admin_row.get("password")
        or admin_row.get("password_temp")
    )

    matched, is_hashed = verify_password(password, stored_value)
    if not matched:
        logger.info(f"Admin login failed (bad password): {mask_email_for_log(email)}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if requires_password_change(admin_row, is_hashed):
        reset_token = create_reset_token(email, str(stored_value) if stored_value else None)
        logger.info(f"Admin login requires password change: {mask_email_for_log(email)}")
        return {
            "ok": True,
            "requires_password_change": True,
            "reset_token": reset_token,
        }

    session_token = create_session_token(email, str(stored_value))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    logger.info(f"Admin login success: {mask_email_for_log(email)}")
    return {"ok": True, "requires_password_change": False, "email": email}


@router.post("/password")
async def admin_update_password(body: AdminPasswordResetRequest, response: Response):
    payload = decode_reset_payload(body.reset_token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    admin_row = fetch_admin_user(email)
    if not admin_row:
        raise HTTPException(status_code=400, detail="Admin not found")

    canonical_email = admin_row.get("email") or email

    if "active" in admin_row and not as_bool(admin_row.get("active")):
        raise HTTPException(status_code=403, detail="Admin access disabled")

    stored_value = (
        admin_row.get("password_hash")
        or admin_row.get("password")
        or admin_row.get("password_temp")
    )
    if not stored_value:
        raise HTTPException(status_code=400, detail="Admin password not set")

    verified = verify_reset_token(body.reset_token, str(stored_value))
    if not verified:
        raise HTTPException(status_code=400, detail="Reset token expired or invalid")

    new_password = (body.new_password or "").strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    new_hash = hash_password(new_password)
    update_payload = build_password_update_payload(admin_row, new_hash)
    updated = update_admin_user(email, update_payload)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update password")

    session_token = create_session_token(canonical_email, new_hash)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    logger.info(f"Admin password updated: {mask_email_for_log(canonical_email)}")
    return {"ok": True, "email": canonical_email}


@router.post("/logout")
async def admin_logout(response: Response):
    response.set_cookie(
        key=SESSION_COOKIE,
        value="",
        max_age=0,
        expires=0,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.get("/pdfs")
async def admin_list_pdfs(request: Request, group: Optional[str] = None, limit: int = 50, offset: int = 0):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        q = (
            admin.table("pdf_assets")
            .select("id,group_key,bucket,path,label,order_index,is_default,score_min,score_max,active,created_at,updated_at")
            .order("group_key", desc=False)
            .order("order_index", desc=False)
        )
        if group:
            q = q.eq("group_key", group)
        if offset:
            q = q.range(offset, offset + max(0, int(limit)) - 1)
        else:
            q = q.limit(max(1, min(int(limit or 50), 200)))
        res = q.execute()
        items = getattr(res, "data", None) or []
        return {"items": items}
    except Exception as e:
        logger.info(f"admin_list_pdfs error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list pdf_assets")


@router.post("/pdfs")
async def admin_create_pdf(request: Request, body: PdfAssetCreate):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        payload = body.dict()
        res = admin.table("pdf_assets").insert(payload).execute()
        data = getattr(res, "data", None) or []
        return {"item": data[0] if data else None}
    except Exception as e:
        logger.info(f"admin_create_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create pdf_asset")


@router.put("/pdfs/{item_id}")
async def admin_update_pdf(item_id: str, request: Request, body: PdfAssetUpdate):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        update = {k: v for k, v in body.dict().items() if v is not None}
        if not update:
            return {"item": None}
        res = admin.table("pdf_assets").update(update).eq("id", item_id).execute()
        data = getattr(res, "data", None) or []
        return {"item": data[0] if data else None}
    except Exception as e:
        logger.info(f"admin_update_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update pdf_asset")


@router.delete("/pdfs/{item_id}")
async def admin_delete_pdf(item_id: str, request: Request):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        res = admin.table("pdf_assets").delete().eq("id", item_id).execute()
        data = getattr(res, "data", None) or []
        return {"deleted": len(data)}
    except Exception as e:
        logger.info(f"admin_delete_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete pdf_asset")




@router.post("/upload-url")
async def admin_create_upload_url(
    request: Request,
    bucket: str = Form(...),
    dest_path: str = Form(""),
    filename: str = Form(...),
):
    """Return a signed upload URL and token for direct browser upload.

    Client should perform a PUT to the returned signed_url with the file body.
    """
    _ = require_admin(request)
    try:
        _public, service_key, supabase_url = build_supabase_public()
        safe_name = filename.split("/")[-1]
        dp = (dest_path or "").strip()
        if dp.endswith("/") or dp == "":
            final_path = (dp + safe_name).lstrip("/")
        else:
            final_path = dp.lstrip("/")
        info = create_signed_upload_url(supabase_url, service_key, bucket, final_path)
        if not info:
            raise HTTPException(status_code=500, detail="Failed to create signed upload URL")
        return {"bucket": bucket, "path": final_path, **info}
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"admin_create_upload_url error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create signed upload URL")
