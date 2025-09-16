import logging
from typing import Optional
from fastapi import HTTPException, Request

from .core_supabase import build_supabase_public

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

