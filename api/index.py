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


@app.post("/submit")
async def submit_form(data: FormData):
    """Example form endpoint used by the frontend demo."""
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


def _fetch_profile_rest(supabase_url: str, service_key: str, user_id: Optional[str] = None, email: Optional[str] = None) -> Optional[dict]:
    """Fetch a single profile row by user id or email using service role REST.

    Returns a dict with at least {id, email, name} if found, else None.
    """
    if not service_key:
        return None

    try:
        base = supabase_url.rstrip("/") + "/rest/v1/profiles"
        params = {"select": "id,email,name", "limit": 1}
        if user_id:
            params["id"] = f"eq.{user_id}"
        elif email:
            params["email"] = f"eq.{email}"
        else:
            return None

        q = _urlparse.urlencode(params)
        url = f"{base}?{q}"
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
        }
        req = _urlreq.Request(url, headers=headers, method="GET")
        with _urlreq.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            data = _json.loads(body)
            # REST returns a list
            if isinstance(data, list) and data:
                item = data[0]
                return {
                    "id": item.get("id"),
                    "email": item.get("email"),
                    "name": item.get("name"),
                }
    except Exception as e:
        logger.info(f"Profile fetch failed: {e}")
    return None


def _check_email_exists_rest(public_client, supabase_url: str, service_key: str, email: str) -> dict:
    """Check if an email already exists in either auth.users or profiles.

    - Uses Admin REST (if `service_key` is available) to search `auth.users`.
    - Queries the `profiles` table via the public client using `ilike` if supported.
    - Returns a dict: {"in_users": bool, "in_profiles": bool}.
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
    """Unified auth endpoint for login and signup.

    - `mode == "login"`: calls Supabase `sign_in_with_password`.
    - `mode == "signup"`: pre-checks for existing email, then calls `sign_up`.
    """
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
            # Try to enrich with profile name (via service role REST if available)
            profile = None
            try:
                uid = getattr(user, "id", None)
                uemail = getattr(user, "email", None)
                profile = _fetch_profile_rest(supabase_url, service_key, user_id=uid, email=uemail)
            except Exception as e:
                logger.info(f"Profile enrichment skipped: {e}")
            # If not found and we have a session, try with the user's access token (RLS)
            try:
                if not profile and session and getattr(session, "access_token", None):
                    token = getattr(session, "access_token", None)
                    base = supabase_url.rstrip("/") + "/rest/v1/profiles"
                    params = {"select": "id,email,name", "limit": 1}
                    if uid:
                        params["id"] = f"eq.{uid}"
                    elif uemail:
                        params["email"] = f"eq.{uemail}"
                    q = _urlparse.urlencode(params)
                    url = f"{base}?{q}"
                    anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
                    headers = {
                        "apikey": anon_key,
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    }
                    req = _urlreq.Request(url, headers=headers, method="GET")
                    with _urlreq.urlopen(req, timeout=10) as resp:
                        body = resp.read().decode("utf-8")
                        data = _json.loads(body)
                        if isinstance(data, list) and data:
                            item = data[0]
                            profile = {
                                "id": item.get("id"),
                                "email": item.get("email"),
                                "name": item.get("name"),
                            }
            except Exception as e:
                logger.info(f"Profile enrichment via token failed: {e}")
            return {
                "mode": mode,
                "user": {"id": getattr(user, "id", None), "email": getattr(user, "email", None)} if user else None,
                "session": {
                    "access_token": getattr(session, "access_token", None),
                    "token_type": getattr(session, "token_type", None),
                    "expires_in": getattr(session, "expires_in", None),
                } if session else None,
                "profile": profile,
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
