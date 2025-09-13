from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Tuple
import os
import logging
import json as _json
from urllib import request as _urlreq
from urllib import parse as _urlparse

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
    logger.info(f"{request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"-> {response.status_code} {request.method} {request.url.path}")
        return response
    except Exception as e:
        logger.exception(f"Unhandled error for {request.method} {request.url.path}: {e}")
        raise


@app.get("/ping")
async def ping():
    return {"ok": True}


@app.get("/")
async def root():
    return {"message": "FastAPI index3 root alive"}


@app.get("/env-check")
async def env_check():
    keys = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]
    result = {}
    for k in keys:
        v = os.getenv(k)
        result[k] = {"present": bool(v), "length": len(v) if v else 0}
    return result


class FormData(BaseModel):
    name: str
    email: str


@app.post("/submit")
async def submit_form(data: FormData):
    logger.info(f"Received data: {data}")
    return {"message": "Data received successfully"}


class AuthData(BaseModel):
    mode: str  # 'login' or 'signup'
    email: str
    password: str
    name: Optional[str] = None


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


def _admin_get_user_by_email_rest(supabase_url: str, service_key: str, email: str) -> bool:
    """Use GoTrue Admin REST to check if a user exists by email.

    Tries a direct email filter first; if unsupported, falls back to listing the first page
    and filtering client-side. Returns True if a match is found (case-insensitive).
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


def _check_email_exists_rest(public_client, supabase_url: str, service_key: str, email: str) -> dict:
    """Combined existence check using Admin REST and profiles table (case-insensitive).

    Returns: {"in_users": bool, "in_profiles": bool}
    """
    exists = {"in_users": False, "in_profiles": False}

    # Admin REST check (only if service key available)
    try:
        if service_key:
            exists["in_users"] = _admin_get_user_by_email_rest(supabase_url, service_key, email)
    except Exception as e:
        logger.info(f"Admin REST check unavailable: {e}")

    # profiles table check (prefer case-insensitive if supported)
    try:
        try:
            q = public_client.table("profiles").select("id").limit(1)
            # try ilike if available
            if hasattr(q, "ilike"):
                q = q.ilike("email", email)
            else:
                q = q.eq("email", email)
            res = q.execute()
            data = getattr(res, "data", None)
            if isinstance(data, list) and len(data) > 0:
                exists["in_profiles"] = True
        except Exception as e:
            logger.info(f"Profiles check failed: {e}")
    except Exception as e:
        logger.info(f"Profiles check unavailable: {e}")

    return exists


@app.post("/auth")
async def auth(data: AuthData):
    mode = (data.mode or "").lower().strip()
    email = _normalize_email(data.email)
    try:
        logger.info(f"Auth request: mode={mode}, email={email}")
    except Exception:
        pass

    if mode not in {"login", "signup"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'login' or 'signup'.")

    public_client, service_key, supabase_url = _build_supabase_public()

    try:
        if mode == "login":
            res = public_client.auth.sign_in_with_password({
                "email": email,
                "password": data.password,
            })
            user = getattr(res, "user", None)
            session = getattr(res, "session", None)
            return {
                "mode": mode,
                "user": {"id": getattr(user, "id", None), "email": getattr(user, "email", None)} if user else None,
                "session": {
                    "access_token": getattr(session, "access_token", None),
                    "token_type": getattr(session, "token_type", None),
                    "expires_in": getattr(session, "expires_in", None),
                } if session else None,
                "message": "Login successful" if session else "Login response received",
            }
        else:
            # Pre-check for existing email in auth.users and profiles
            exists = _check_email_exists_rest(public_client, supabase_url, service_key, email)
            if exists.get("in_users") or exists.get("in_profiles"):
                raise HTTPException(
                    status_code=409,
                    detail="Email already registered. Please log in instead.",
                )

            payload = {
                "email": email,
                "password": data.password,
            }
            if data.name:
                payload["options"] = {"data": {"name": data.name}}

            res = public_client.auth.sign_up(payload)
            user = getattr(res, "user", None)
            session = getattr(res, "session", None)
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
        if any(s in msg.lower() for s in ["already registered", "user exists", "duplicate", "email already in use"]):
            raise HTTPException(status_code=409, detail="Email already registered. Please log in instead.")
        raise HTTPException(status_code=400, detail=msg)


# Fallback root handler to support platform rewrites that drop subpaths
@app.post("/")
async def auth_root(data: AuthData):
    return await auth(data)


# Catch-all POST to support rewrites preserving subpaths
@app.post("/{_path:path}")
async def auth_any_path(_path: str, data: AuthData):
    return await auth(data)


# Also provide GET catch-all to confirm routing without requiring body
@app.get("/{_path:path}")
async def get_any_path(_path: str):
    return {"route": _path or "/", "message": "FastAPI index3 alive"}

