from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Tuple, Dict, Any
import os
import logging
import json as _json
from urllib import request as _urlreq
from urllib import parse as _urlparse
import base64 as _b64

try:
    # RSA decryption for client-side encrypted payloads
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
except Exception:
    serialization = None

try:
    # Supabase Python client (v2)
    from supabase import create_client
except Exception:
    create_client = None  # Will raise at runtime if not installed


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api3")

app = FastAPI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Simple request logging middleware.

    - Logs the incoming method + path for every request.
    - Calls the downstream handler and logs the final status code.
    - Captures and logs unhandled exceptions before re-raising.
    """
    logger.info(f"{request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"-> {response.status_code} {request.method} {request.url.path}")
        return response
    except Exception as e:
        logger.exception(f"Unhandled error for {request.method} {request.url.path}: {e}")
        raise


@app.get("/")
async def root():
    """Basic liveness endpoint for the function root.

    Note: This is reachable at the function base path (e.g. `/api`).
    """
    return {"message": "FastAPI index3 root alive"}



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


def _normalize_email(email: str) -> str:
    try:
        return (email or "").strip().lower()
    except Exception:
        return email


def _build_supabase_public() -> Tuple[object, str, str]:
    """Create a public Supabase client and return (client, service_key, supabase_url).
    service_key is returned to enable admin REST calls when available; may be empty string.
    """
    if create_client is None:
        raise HTTPException(status_code=500, detail="Supabase client not installed on server.")

    supabase_url = os.getenv("SUPABASE_URL") or ""
    anon_key = os.getenv("SUPABASE_ANON_KEY") or ""
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""

    if not supabase_url or not (anon_key or service_key):
        raise HTTPException(status_code=500, detail="Supabase environment not configured.")

    try:
        public_client = create_client(supabase_url, anon_key or service_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize Supabase client: {e}")

    return public_client, service_key, supabase_url


def _load_private_key() -> Optional[object]:
    """Load RSA private key from env var `AUTH_PRIVATE_KEY_PEM` or `api/keys/private_key.pem`.

    Returns a cryptography private key object, or None if unavailable.
    """
    if serialization is None:
        return None
    pem = os.getenv("AUTH_PRIVATE_KEY_PEM")
    if pem:
        try:
            # Support envs that store PEM with escaped newlines
            if "\\n" in pem and "\n" not in pem:
                pem = pem.replace("\\n", "\n")
            key = serialization.load_pem_private_key(
                pem.encode("utf-8"), password=None, backend=default_backend()
            )
            return key
        except Exception:
            pass
    # Try file fallback
    file_path = os.path.join(os.path.dirname(__file__), "keys", "private_key.pem")
    try:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                key = serialization.load_pem_private_key(
                    f.read(), password=None, backend=default_backend()
                )
                return key
    except Exception:
        pass
    return None


def _decrypt_auth_payload(enc_b64: str) -> Optional[Dict[str, Any]]:
    """Decrypt base64-encoded RSA-OAEP (SHA-256) payload containing JSON.

    Expected JSON shape: { email, password, first_name?, last_name? }
    Returns dict or None if decryption fails or key missing.
    """
    try:
        if not enc_b64:
            return None
        priv = _load_private_key()
        if priv is None:
            logger.warning("AUTH_PRIVATE_KEY not available; cannot decrypt 'enc' payload")
            return None
        ciphertext = _b64.b64decode(enc_b64)
        plaintext = priv.decrypt(
            ciphertext,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        data = _json.loads(plaintext.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception as e:
        logger.info(f"Decryption failed: {e}")
        return None


def _mask_email_for_log(email: str) -> str:
    try:
        if not email:
            return ""
        parts = email.split("@", 1)
        user = parts[0]
        domain = parts[1] if len(parts) > 1 else ""
        first = (user[:1] or "*")
        last = (user[-1:] or "*")
        return f"{first}***{last}@{domain}" if domain else f"{first}***{last}"
    except Exception:
        return "***"


def _admin_get_user_by_email_rest(supabase_url: str, service_key: str, email: str) -> bool:
    """Check auth.users for a matching email via GoTrue Admin REST.

    - If a direct `?email=` filter is supported by the deployment, use it.
    - Otherwise, fetch the first page of users and filter by email locally.
    - Returns True if a case-insensitive match is found; False otherwise.
    """
    if not service_key:
        return False

    base = supabase_url.rstrip("/") + "/auth/v1/admin/users"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    email_q = _urlparse.urlencode({"email": email})
    url = f"{base}?{email_q}"

    def _fetch_json(u: str):
        req = _urlreq.Request(u, headers=headers, method="GET")
        with _urlreq.urlopen(req, timeout=10) as resp:
            body = resp.read()
            ct = resp.headers.get("content-type", "")
            if "application/json" not in ct and not body.strip().startswith(b"{") and not body.strip().startswith(b"["):
                raise ValueError("Non-JSON admin response")
            return _json.loads(body.decode("utf-8"))

    try:
        data = _fetch_json(url)
        # Possible shapes: list of users, or object with 'users'/'data'
        if isinstance(data, list):
            return any(((u.get("email") or "").lower() == email.lower()) for u in data)
        if isinstance(data, dict):
            arr = data.get("users") or data.get("data") or []
            if isinstance(arr, list):
                return any(((getattr(u, "email", None) or u.get("email") or "").lower() == email.lower()) for u in arr)
            # If a single user object is returned
            if data.get("email"):
                return (data.get("email") or "").lower() == email.lower()
    except Exception as e:
        logger.info(f"Admin email filter unsupported or failed: {e}")

    # Fallback: list first page and filter client-side
    try:
        list_url = f"{base}?page=1&per_page=200"
        data = _fetch_json(list_url)
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("users") or data.get("data") or []
        return any(((getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else None) or "").lower() == email.lower()) for u in items)
    except Exception as e:
        logger.info(f"Admin list users failed: {e}")
        return False


def _fetch_profile_admin_sdk(supabase_url: str, service_key: str, user_id: Optional[str] = None, email: Optional[str] = None) -> Optional[dict]:
    """Fetch a single profile using the Supabase Python client with service role key.

    This avoids URL quirks with PostgREST and leverages the SDK.
    """
    if not service_key or create_client is None:
        return None
    try:
        admin_client = create_client(supabase_url, service_key)
        # Try first_name/last_name first; fallback to full_name; final fallback to name
        selectors = [
            "id,first_name,last_name,full_name",
            "id,full_name",
            "id,name",
        ]
        for sel in selectors:
            try:
                q = admin_client.table("profiles").select(sel).limit(1)
                if user_id:
                    q = q.eq("id", user_id)
                elif email:
                    q = q.eq("email", email)
                else:
                    return None
                res = q.execute()
                data = getattr(res, "data", None)
                if isinstance(data, list) and data:
                    item = data[0]
                    return {
                        "id": item.get("id"),
                        "first_name": item.get("first_name"),
                        "last_name": item.get("last_name"),
                        "full_name": item.get("full_name") or item.get("name"),
                    }
            except Exception as _e:
                # try next selector
                continue
    except Exception as e:
        logger.info(f"Profile fetch (SDK) failed: {e}")
    return None


def _check_email_exists_rest(public_client, supabase_url: str, service_key: str, email: str) -> dict:
    """Deprecated: Previously checked both auth.users and profiles by email.

    Kept for backward compatibility but now only checks `auth.users` via
    admin REST (when `service_key` is available). Prefer calling
    `_admin_get_user_by_email_rest` directly where possible.
    """
    result = {"in_users": False, "in_profiles": False}
    try:
        if service_key:
            result["in_users"] = _admin_get_user_by_email_rest(supabase_url, service_key, email)
    except Exception as e:
        logger.info(f"Admin REST check unavailable: {e}")
    return result


@app.post("/auth")
async def auth(data: AuthData):
    """Unified auth endpoint for login and signup.

    - `mode == "login"`: calls Supabase `sign_in_with_password`.
    - `mode == "signup"`: pre-checks for existing email, then calls `sign_up`.
    """
    mode = (data.mode or "").lower().strip()
    # Prefer encrypted payload when available
    decrypted = _decrypt_auth_payload(data.enc) if getattr(data, "enc", None) else None
    if getattr(data, "enc", None) and decrypted is None:
        raise HTTPException(status_code=400, detail="Invalid encrypted payload")
    email = _normalize_email((decrypted or {}).get("email") or (data.email or ""))
    password = (decrypted or {}).get("password") or data.password or ""
    first_name = (decrypted or {}).get("first_name") or data.first_name
    last_name = (decrypted or {}).get("last_name") or data.last_name
    try:
        logger.info(f"Auth request: mode={mode}, email={_mask_email_for_log(email)}")
    except Exception:
        pass

    if mode not in {"login", "signup"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'login' or 'signup'.")

    public_client, service_key, supabase_url = _build_supabase_public()

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
                profile = _fetch_profile_admin_sdk(supabase_url, service_key, user_id=uid, email=uemail)
                
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
            return {
                "mode": mode,
                "user": {
                    "id": getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None),
                    "email": getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None),
                    "user_metadata": (meta_dict if meta_dict else None),
                } if user else None,
                "session": {
                    "access_token": getattr(session, "access_token", None),
                    "token_type": getattr(session, "token_type", None),
                    "expires_in": getattr(session, "expires_in", None),
                } if session else None,
                "profile": profile,
                "message": "Login successful" if session else "Login response received",
            }
        else:
            # Pre-check only against auth.users using Admin REST when available
            if service_key and _admin_get_user_by_email_rest(supabase_url, service_key, email):
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
                    admin_client = create_client(supabase_url, service_key)
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
async def auth_root(data: AuthData):
    """Accept POSTs at the root and forward to `/auth` semantics."""
    return await auth(data)


# Catch-all POST to support rewrites preserving subpaths
@app.post("/{_path:path}")
async def auth_any_path(_path: str, data: AuthData):
    """Accept POSTs at any subpath and forward to `auth`.
    Doesn NOT work without this on Vercel !!!

    Useful when the hosting platform (e.g., Vercel) rewrites various
    `/api/:path*` routes to this function. This ensures clients can POST
    to alternate paths (like `/api/login` or `/api/signup`) and still hit
    the same handler.
    """
    return await auth(data)


# Also provide GET catch-all to confirm routing without requiring body
@app.get("/{_path:path}")
async def get_any_path(_path: str):
    """Simple GET responder for any path; helpful for routing checks."""
    return {"route": _path or "/", "message": "FastAPI index3 alive"}
