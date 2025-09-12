from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import os
import logging

try:
    # v2 Python client
    from supabase import create_client
except Exception:
    create_client = None  # Will raise at runtime if not installed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

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
    return {"message": "FastAPI root alive"}


@app.get("/env-check")
async def env_check():
    # Do not leak values, only presence and length
    keys = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]
    result = {}
    for k in keys:
        v = os.getenv(k)
        result[k] = {
            "present": bool(v),
            "length": len(v) if v else 0,
        }
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


def _check_email_exists(client, email: str) -> dict:
    """Best-effort existence check in auth.users (admin) and profiles table.

    Returns a dict {"in_users": bool, "in_profiles": bool}.
    Never raises; logs and falls back to False if checks fail.
    """
    exists = {"in_users": False, "in_profiles": False}

    # Check auth.users via Admin API if service role key is used
    try:
        # Some environments may not expose admin APIs when using anon key
        admin = getattr(client.auth, "admin", None)
        if admin is not None:
            try:
                res = admin.get_user_by_email(email)
                # Different client versions may shape the response differently
                user_obj = getattr(res, "user", None) or getattr(res, "data", None) or res
                if user_obj:
                    exists["in_users"] = True
            except Exception as e:
                # If it's a not-found, treat as False; otherwise log and continue
                msg = str(e).lower()
                if "not found" in msg or "no user" in msg:
                    pass
                else:
                    logger.info(f"Admin get_user_by_email failed: {e}")
    except Exception as e:
        logger.info(f"Auth admin check unavailable: {e}")

    # Check profiles table if present and email column exists
    try:
        try:
            res = (
                client.table("profiles")
                .select("id")
                .eq("email", email)
                .limit(1)
                .execute()
            )
            data = getattr(res, "data", None)
            if isinstance(data, list) and len(data) > 0:
                exists["in_profiles"] = True
        except Exception as e:
            # Table might not exist or column may differ; log and continue
            logger.info(f"Profiles check failed: {e}")
    except Exception as e:
        logger.info(f"Profiles check unavailable: {e}")

    return exists


@app.post("/auth")
async def auth(data: AuthData):
    mode = data.mode.lower().strip()
    # Log high-level auth intent without sensitive data
    try:
        logger.info(f"Auth request: mode={mode}, email={data.email}")
    except Exception:
        pass
    if mode not in {"login", "signup"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'login' or 'signup'.")

    # Ensure Supabase client is available
    if create_client is None:
        raise HTTPException(status_code=500, detail="Supabase client not installed on server.")

    supabase_url = os.getenv("SUPABASE_URL")
    # Prefer service role if provided; otherwise fall back to anon key
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        raise HTTPException(status_code=500, detail="Supabase environment not configured.")

    try:
        client = create_client(supabase_url, supabase_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize Supabase client: {e}")

    try:
        if mode == "login":
            res = client.auth.sign_in_with_password({
                "email": data.email,
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
            # Normalize email before any checks
            normalized_email = _normalize_email(data.email)

            # Pre-check for existing email in auth.users and profiles
            exists = _check_email_exists(client, normalized_email)
            if exists.get("in_users") or exists.get("in_profiles"):
                raise HTTPException(
                    status_code=409,
                    detail="Email already registered. Please log in instead.",
                )

            payload = {
                "email": normalized_email,
                "password": data.password,
            }
            # Attach user metadata if name provided
            if data.name:
                payload["options"] = {"data": {"name": data.name}}

            res = client.auth.sign_up(payload)
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
        # If Supabase indicates duplicate email, map to 409 with friendly message
        msg = str(e)
        if any(s in msg.lower() for s in ["already registered", "user exists", "duplicate", "email already in use"]):
            raise HTTPException(status_code=409, detail="Email already registered. Please log in instead.")
        # Bubble up as a 400 for other auth failures
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
    return {"route": _path or "/", "message": "FastAPI alive"}
