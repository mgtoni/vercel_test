import logging
from typing import Optional, Dict
from fastapi import HTTPException, Request

from .core_supabase import build_supabase_public, create_signed_upload_url

logger = logging.getLogger("api3.admin_checks")


def require_admin(request: Request) -> str:
    """Ensure the current session user is an active admin.

    Returns the admin email on success; raises HTTPException otherwise.
    """
    try:
        token = request.cookies.get("sb_access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        public_client, service_key, supabase_url = build_supabase_public()
        user_res = public_client.auth.get_user(token)
        user = getattr(user_res, "user", None)
        email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
        if not email:
            raise HTTPException(status_code=401, detail="Invalid session")

        # Check admin_users table for active admin
        try:
            from supabase import create_client as _create_client
            admin = _create_client(supabase_url, service_key)
            res = (
                admin.table("admin_users")
                .select("email, active")
                .eq("email", email)
                .eq("active", True)
                .limit(1)
                .execute()
            )
            data = getattr(res, "data", None) or []
            if not data:
                raise HTTPException(status_code=403, detail="Not authorized")
        except HTTPException:
            raise
        except Exception as e:
            logger.info(f"admin table check failed: {e}")
            raise HTTPException(status_code=500, detail="Admin check failed")

        return email
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"require_admin error: {e}")
        raise HTTPException(status_code=401, detail="Admin verification failed")


def normalize_admin_path(value: Optional[str]) -> str:
    """Normalize admin path fragments for routing checks.

    Returns a lowercase path without leading/trailing slashes.
    """
    if value is None:
        return ""
    cleaned = str(value).replace('\\', '/').strip()
    if not cleaned:
        return ""
    cleaned = cleaned.split('?', 1)[0]
    cleaned = cleaned.lstrip('/')
    cleaned = cleaned.rstrip('/')
    return cleaned.lower()


async def handle_admin_upload(request: Request) -> Dict[str, str]:
    """Validate admin permissions and return a signed upload URL payload."""
    try:
        require_admin(request)
        form = await request.form()
        bucket = (form.get("bucket") or "").strip()
        dest_path = (form.get("dest_path") or "").strip()
        filename = (form.get("filename") or "").strip()
        if not bucket or not filename:
            raise HTTPException(status_code=400, detail="bucket and filename are required")
        safe_name = filename.split("/")[-1]
        if dest_path.endswith("/") or dest_path == "":
            final_path = (dest_path + safe_name).lstrip("/")
        else:
            final_path = dest_path.lstrip("/")
        _public, service_key, supabase_url = build_supabase_public()
        info = create_signed_upload_url(supabase_url, service_key, bucket, final_path)
        if not info:
            raise HTTPException(status_code=500, detail="Failed to create signed upload URL")
        return {"bucket": bucket, "path": final_path, **info}
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"admin/upload-url error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create signed upload URL")
