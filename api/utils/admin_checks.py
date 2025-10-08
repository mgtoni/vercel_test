import logging
from typing import Optional, Dict
from fastapi import HTTPException, Request

from .admin_auth import (
    SESSION_COOKIE,
    as_bool,
    decode_session_payload,
    fetch_admin_user,
    requires_password_change,
    verify_session_token,
)
from .core_supabase import build_supabase_public, create_signed_upload_url

logger = logging.getLogger("api3.admin_checks")


def require_admin(request: Request) -> str:
    """Ensure the current session user is an active admin.

    Returns the admin email on success; raises HTTPException otherwise.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_session_payload(token)
    email = (payload or {}).get("email") if payload else None
    if not email:
        raise HTTPException(status_code=401, detail="Invalid session")

    admin_row = fetch_admin_user(email)
    if not admin_row:
        raise HTTPException(status_code=401, detail="Admin not found")

    if "active" in admin_row and not as_bool(admin_row.get("active")):
        raise HTTPException(status_code=403, detail="Admin access disabled")

    stored_hash = admin_row.get("password_hash")
    if not stored_hash or not str(stored_hash).startswith("$2"):
        raise HTTPException(status_code=401, detail="Admin session invalidated")

    session_data = verify_session_token(token, str(stored_hash))
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")

    if requires_password_change(admin_row, True):
        raise HTTPException(status_code=403, detail="Password update required")

    return email


def normalize_admin_path(value: Optional[str]) -> str:
    """Normalize admin path fragments for routing checks.

    Returns a lowercase path with the admin portion prioritized.
    """
    if value is None:
        return ""
    cleaned = str(value).replace('\\', '/').strip()
    if not cleaned:
        return ""
    cleaned = cleaned.split('?', 1)[0]
    parts = [segment for segment in cleaned.strip('/').split('/') if segment]
    if not parts:
        return ""
    try:
        admin_index = parts.index('admin')
        parts = parts[admin_index:]
    except ValueError:
        pass
    return '/'.join(parts).lower()


async def handle_admin_upload(request: Request) -> Dict[str, str]:
    """Validate admin permissions and return a signed upload URL payload."""
    try:
        require_admin(request)
        form = await request.form()
        module = (form.get("module") or "").strip()
        lesson = (form.get("lesson") or "").strip()
        filename = (form.get("filename") or "").strip()
        if not module or not filename:
            raise HTTPException(status_code=400, detail="module and filename are required")
        safe_name = filename.split("/")[-1]
        if lesson.endswith("/") or lesson == "":
            final_path = (lesson + safe_name).lstrip("/")
        else:
            final_path = lesson.lstrip("/")
        _public, service_key, supabase_url = build_supabase_public()
        info = create_signed_upload_url(supabase_url, service_key, module, final_path)
        if not info:
            raise HTTPException(status_code=500, detail="Failed to create signed upload URL")
        return {"module": module, "path": final_path, **info}
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"admin/upload-url error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create signed upload URL")
