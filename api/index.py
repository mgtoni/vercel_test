from fastapi import FastAPI, HTTPException, Request, Response
import logging
from typing import Dict, Any, Optional

from .models import AuthData, ProfileReq, PdfAssetCreate, PdfAssetUpdate
from .utils.crypto_utils import (
    decrypt_auth_payload,
    aesgcm_encrypt_profile,
    mask_email_for_log,
)
from .utils.supabase_utils import (
    build_supabase_public,
    admin_get_user_by_email_rest,
    fetch_profile_admin_sdk,
    fetch_pdfs_from_manifest,
)
from .middleware import log_requests
from .utils.common import normalize_email


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api3")

app = FastAPI()


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    return await log_requests(request, call_next)


@app.get("/")
async def root():
    """Basic liveness endpoint for the function root.

    Note: This is reachable at the function base path (e.g. `/api`).
    """
    return {"message": "FastAPI index3 root alive"}



"""Keep only route handlers and lightweight glue in this file."""




@app.post("/auth")
async def auth(data: AuthData, response: Response):
    """Unified auth endpoint for login and signup.

    - `mode == "login"`: calls Supabase `sign_in_with_password`.
    - `mode == "signup"`: pre-checks for existing email, then calls `sign_up`.
    """
    mode = (data.mode or "").lower().strip()
    # Prefer encrypted payload when available
    decrypted = decrypt_auth_payload(data.enc) if getattr(data, "enc", None) else None
    if getattr(data, "enc", None) and decrypted is None:
        raise HTTPException(status_code=400, detail="Invalid encrypted payload")
    email = normalize_email((decrypted or {}).get("email") or (data.email or ""))
    password = (decrypted or {}).get("password") or data.password or ""
    first_name = (decrypted or {}).get("first_name") or data.first_name
    last_name = (decrypted or {}).get("last_name") or data.last_name
    return_key_b64 = (decrypted or {}).get("rtk") or None
    try:
        logger.info(f"Auth request: mode={mode}, email={mask_email_for_log(email)}")
    except Exception:
        pass

    if mode not in {"login", "signup"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'login' or 'signup'.")

    try:
        public_client, service_key, supabase_url = build_supabase_public()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        if mode == "login":
            res = public_client.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
            user = getattr(res, "user", None)
            session = getattr(res, "session", None)
            # Try to enrich with profile name (via service role REST if available)
            profile = None
            try:
                uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
                uemail = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
                # Prefer SDK with service role
                profile = fetch_profile_admin_sdk(supabase_url, service_key, user_id=uid, email=uemail)
                
            except Exception as e:
                logger.info(f"Profile enrichment skipped: {e}")
            # No REST fallback; SDK-only per requirements
            # Fallback to user metadata name if present
            user_meta_name = None
            meta_dict = {}
            try:
                if isinstance(user, dict):
                    meta_dict = (user.get("user_metadata") or {})
                    user_meta_name = meta_dict.get("name") or (" ".join([
                        (meta_dict.get("first_name") or "").strip(),
                        (meta_dict.get("last_name") or "").strip(),
                    ])).strip()
                else:
                    um = getattr(user, "user_metadata", None)
                    if isinstance(um, dict):
                        meta_dict = um
                        user_meta_name = um.get("name") or (" ".join([
                            (um.get("first_name") or "").strip(),
                            (um.get("last_name") or "").strip(),
                        ])).strip()
            except Exception:
                user_meta_name = None
            if user_meta_name and isinstance(meta_dict, dict) and "name" not in meta_dict:
                meta_dict["name"] = user_meta_name
            # Build PII object, but do not include plaintext in response
            fn = (profile or {}).get("first_name") or (meta_dict or {}).get("first_name") or None
            ln = (profile or {}).get("last_name") or (meta_dict or {}).get("last_name") or None
            full_name = None
            if (profile or {}).get("full_name"):
                full_name = (profile or {}).get("full_name")
            elif (meta_dict or {}).get("name"):
                full_name = (meta_dict or {}).get("name")
            else:
                full_name = (f"{(fn or '').strip()} {(ln or '').strip()}").strip()

            pii = {
                "first_name": fn,
                "last_name": ln,
                "name": full_name,
                # Avoid returning email in plaintext
                "email": getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None),
            }
            enc_blob = aesgcm_encrypt_profile(return_key_b64, pii)
            # Set a session cookie with Supabase access token (session cookie, HttpOnly)
            try:
                if session and getattr(session, "access_token", None):
                    response.set_cookie(
                        key="sb_access_token",
                        value=getattr(session, "access_token"),
                        httponly=True,
                        secure=True,
                        samesite="lax",
                        path="/",
                    )
            except Exception:
                pass
            # Response omits plaintext PII and user_metadata
            return {
                "mode": mode,
                "user": {
                    "id": getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None),
                } if user else None,
                "session": {
                    "access_token": getattr(session, "access_token", None),
                    "token_type": getattr(session, "token_type", None),
                    "expires_in": getattr(session, "expires_in", None),
                } if session else None,
                **({"enc_profile": enc_blob["enc_profile"], "iv": enc_blob["iv"], "alg": enc_blob.get("alg", "AES-GCM")} if enc_blob else {}),
                "message": "Login successful" if session else "Login response received",
            }
        else:
            # Pre-check only against auth.users using Admin REST when available
            if service_key and admin_get_user_by_email_rest(supabase_url, service_key, email):
                raise HTTPException(
                    status_code=409,
                    detail="Email already registered. Please log in instead.",
                )

            # Enforce first_name and last_name on signup
            if not (first_name and str(first_name).strip()) or not (last_name and str(last_name).strip()):
                raise HTTPException(status_code=400, detail="first_name and last_name are required for signup")

            payload = {
                "email": email,
                "password": password,
            }
            metadata = {
                "first_name": str(first_name).strip(),
                "last_name": str(last_name).strip(),
                "name": f"{str(first_name).strip()} {str(last_name).strip()}".strip(),
            }
            payload["options"] = {"data": metadata}

            res = public_client.auth.sign_up(payload)
            user = getattr(res, "user", None)
            session = getattr(res, "session", None)
            # Create or update profiles row via admin client if available
            try:
                if service_key and user:
                    from supabase import create_client as _create_client
                    admin_client = _create_client(supabase_url, service_key)
                    uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
                    profile_payload = {
                        "id": uid,
                        "first_name": str(first_name).strip(),
                        "last_name": str(last_name).strip(),
                        "full_name": (f"{str(first_name).strip()} {str(last_name).strip()}").strip(),
                    }
                    try:
                        admin_client.table("profiles").upsert(profile_payload).execute()
                    except Exception:
                        # fallback to only full_name for older schemas
                        try:
                            admin_client.table("profiles").upsert({
                                "id": uid,
                                "full_name": profile_payload["full_name"],
                            }).execute()
                        except Exception as e2:
                            logger.info(f"Profiles upsert failed: {e2}")
            except Exception as e:
                logger.info(f"Profiles creation skipped: {e}")
            return {
                "mode": mode,
                "user": {"id": getattr(user, "id", None), "email": getattr(user, "email", None)} if user else None,
                "session": {
                    "access_token": getattr(session, "access_token", None),
                    "token_type": getattr(session, "token_type", None),
                    "expires_in": getattr(session, "expires_in", None),
                } if session else None,
                "message": "Signup initiated" if user else "Signup response received",
            }
    except Exception as e:
        msg = str(e)
        raise HTTPException(status_code=409, detail=msg)
        
        #if any(s in msg.lower() for s in ["already registered", "user exists", "duplicate", "email already in use"]):
        #    raise HTTPException(status_code=409, detail="Email already registered. Please log in instead.")
        raise HTTPException(status_code=400, detail=msg)


# Fallback root handler to support platform rewrites that drop subpaths
@app.post("/")
async def auth_root(data: AuthData, response: Response):
    """Accept POSTs at the root and forward to `/auth` semantics."""
    return await auth(data, response)


# Catch-all POST to support rewrites preserving subpaths
@app.post("/{_path:path}")
async def auth_any_path(_path: str, data: AuthData, response: Response):
    """Accept POSTs at any subpath and forward to `auth`.
    Doesn NOT work without this on Vercel !!!

    Useful when the hosting platform (e.g., Vercel) rewrites various
    `/api/:path*` routes to this function. This ensures clients can POST
    to alternate paths (like `/api/login` or `/api/signup`) and still hit
    the same handler.
    """
    return await auth(data, response)


# Also provide GET catch-all to confirm routing without requiring body
@app.get("/{_path:path}")
async def get_any_path(_path: str):
    """Simple GET responder for any path; helpful for routing checks."""
    return {"route": _path or "/", "message": "FastAPI index3 alive"}


@app.post("/profile")
async def get_profile(req: ProfileReq, request: Request):
    """Return encrypted profile info for the current session.

    Auth via session cookie `sb_access_token` set during login.
    The client supplies a base64 AES key `rtk` used only to encrypt the response.
    """
    try:
        token = request.cookies.get("sb_access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        try:
            public_client, service_key, supabase_url = build_supabase_public()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        # Validate token and get user
        user_res = public_client.auth.get_user(token)
        user = getattr(user_res, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")

        uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
        uemail = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)

        # Enrich profile using service role SDK when available
        profile = fetch_profile_admin_sdk(supabase_url, service_key, user_id=uid, email=uemail)

        # Build PII object
        meta_dict = {}
        try:
            if isinstance(user, dict):
                meta_dict = (user.get("user_metadata") or {})
            else:
                um = getattr(user, "user_metadata", None)
                if isinstance(um, dict):
                    meta_dict = um
        except Exception:
            meta_dict = {}

        fn = (profile or {}).get("first_name") or (meta_dict or {}).get("first_name") or None
        ln = (profile or {}).get("last_name") or (meta_dict or {}).get("last_name") or None
        full_name = None
        if (profile or {}).get("full_name"):
            full_name = (profile or {}).get("full_name")
        elif (meta_dict or {}).get("name"):
            full_name = (meta_dict or {}).get("name")
        else:
            full_name = (f"{(fn or '').strip()} {(ln or '').strip()}").strip()

        pii = {
            "first_name": fn,
            "last_name": ln,
            "name": full_name,
            "email": uemail,
        }

        enc_blob = aesgcm_encrypt_profile(req.rtk, pii)
        if not enc_blob:
            raise HTTPException(status_code=400, detail="Encryption unavailable")

        return {"enc_profile": enc_blob["enc_profile"], "iv": enc_blob["iv"], "alg": enc_blob.get("alg", "AES-GCM")}
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"/profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch profile")


@app.get("/pdfs")
async def list_pdfs(group: str, score: Optional[int] = None, limit: int = 10):
    """List PDFs from DB-backed manifest for a group and optional score.

    Query params:
    - group (required): logical grouping key, e.g. 'profile'
    - score (optional): integer score to match score_min/max ranges
    - limit (optional): max items to return (default 10)
    """
    try:
        limit = max(1, min(int(limit or 10), 100))
    except Exception:
        limit = 10

    try:
        items = fetch_pdfs_from_manifest(group=group, score=score, limit=limit)
        return {"items": items}
    except Exception as e:
        logger.info(f"/pdfs manifest error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch PDFs from manifest")


# --- Admin helpers and endpoints for managing pdf_assets ---
def _require_admin_email(request: Request) -> str:
    """Validate user via Supabase session cookie and ensure email is in ADMIN_EMAILS.

    Returns the admin email on success; raises HTTPException otherwise.
    """
    import os
    allowed_raw = os.getenv("ADMIN_EMAILS") or ""
    allowed = {e.strip().lower() for e in allowed_raw.split(",") if e.strip()}
    if not allowed:
        # If not configured, deny access by default
        raise HTTPException(status_code=403, detail="Admin access not configured")

    try:
        token = request.cookies.get("sb_access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        public_client, _service_key, _url = build_supabase_public()
        user_res = public_client.auth.get_user(token)
        user = getattr(user_res, "user", None)
        email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
        if not email or email.lower() not in allowed:
            raise HTTPException(status_code=403, detail="Not authorized")
        return email
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Admin check failed: {e}")
        raise HTTPException(status_code=401, detail="Admin verification failed")


@app.get("/admin/pdfs")
async def admin_list_pdfs(request: Request, group: Optional[str] = None, limit: int = 50, offset: int = 0):
    _ = _require_admin_email(request)
    try:
        from supabase import create_client as _create_client
        public_client, service_key, supabase_url = build_supabase_public()
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


@app.post("/admin/pdfs")
async def admin_create_pdf(request: Request, body: PdfAssetCreate):
    _ = _require_admin_email(request)
    try:
        from supabase import create_client as _create_client
        public_client, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        payload = body.dict()
        res = admin.table("pdf_assets").insert(payload).execute()
        data = getattr(res, "data", None) or []
        return {"item": data[0] if data else None}
    except Exception as e:
        logger.info(f"admin_create_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create pdf_asset")


@app.put("/admin/pdfs/{item_id}")
async def admin_update_pdf(item_id: str, request: Request, body: PdfAssetUpdate):
    _ = _require_admin_email(request)
    try:
        from supabase import create_client as _create_client
        public_client, service_key, supabase_url = build_supabase_public()
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


@app.delete("/admin/pdfs/{item_id}")
async def admin_delete_pdf(item_id: str, request: Request):
    _ = _require_admin_email(request)
    try:
        from supabase import create_client as _create_client
        public_client, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        res = admin.table("pdf_assets").delete().eq("id", item_id).execute()
        data = getattr(res, "data", None) or []
        return {"deleted": len(data)}
    except Exception as e:
        logger.info(f"admin_delete_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete pdf_asset")
