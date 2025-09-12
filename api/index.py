from fastapi import FastAPI, HTTPException, Request
from typing import Optional
import os
import logging

# Pydantic v1/v2 compatibility imports
try:  # Prefer Pydantic v2 APIs
    from pydantic import BaseModel, EmailStr
    from pydantic import field_validator as _field_validator
    _PD_V2 = True
except Exception:  # Fallback to Pydantic v1
    from pydantic import BaseModel, EmailStr
    from pydantic import validator as _field_validator  # type: ignore
    _PD_V2 = False

try:
    # Supabase Python client (v2)
    from supabase import create_client
except Exception:
    create_client = None  # Will raise at runtime if not installed


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api2")

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
    return {"message": "FastAPI index2 root alive"}


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


def _normalize_email(email: str) -> str:
    try:
        return (email or "").strip().lower()
    except Exception:
        return email


class AuthData(BaseModel):
    """Request body for authentication routes.

    Improvements vs index.py:
    - Uses EmailStr for basic email format validation
    - Normalizes email to lowercase and trims whitespace via validator
    """

    mode: str  # 'login' or 'signup'
    email: EmailStr
    password: str
    name: Optional[str] = None

    if _PD_V2:
        @_field_validator("email")  # type: ignore[misc]
        @classmethod
        def _normalize_email_v2(cls, v: EmailStr):
            return EmailStr(_normalize_email(str(v)))
    else:
        @_field_validator("email", pre=True)  # type: ignore[misc]
        def _normalize_email_v1(cls, v):  # type: ignore[no-redef]
            try:
                return _normalize_email(str(v))
            except Exception:
                return v


def _build_supabase_clients():
    """Create least-privilege and admin clients when possible.

    Returns (public_client, admin_client, using_service_role: bool)
    """
    if create_client is None:
        raise HTTPException(status_code=500, detail="Supabase client not installed on server.")

    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not (anon_key or service_key):
        raise HTTPException(status_code=500, detail="Supabase environment not configured.")

    try:
        public_client = create_client(supabase_url, anon_key or service_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize Supabase public client: {e}")

    admin_client = None
    using_service = bool(service_key)
    if service_key:
        try:
            admin_client = create_client(supabase_url, service_key)
        except Exception as e:
            # If admin client fails, continue with public-only
            logger.info(f"Failed to initialize Supabase admin client: {e}")
            admin_client = None
            using_service = False

    return public_client, admin_client, using_service


def _check_email_exists(admin_client, public_client, email: str) -> dict:
    """Best-effort existence check in auth.users (admin) and profiles table.

    - Uses admin API only when a service-role client is available
    - Uses case-insensitive match (ilike) for profiles
    Returns: {"in_users": bool, "in_profiles": bool}
    """
    exists = {"in_users": False, "in_profiles": False}

    # Check auth.users via Admin API only if we truly have admin client
    if admin_client is not None:
        try:
            admin = getattr(admin_client.auth, "admin", None)
            if admin is not None:
                try:
                    res = admin.get_user_by_email(email)
                    user_obj = getattr(res, "user", None) or getattr(res, "data", None) or res
                    if user_obj:
                        exists["in_users"] = True
                except Exception as e:
                    msg = str(e).lower()
                    if "not found" in msg or "no user" in msg:
                        pass
                    else:
                        logger.info(f"Admin get_user_by_email failed: {e}")
        except Exception as e:
            logger.info(f"Auth admin check unavailable: {e}")

    # Check profiles table (case-insensitive)
    try:
        try:
            res = (
                public_client.table("profiles")
                .select("id")
                .ilike("email", email)  # case-insensitive exact match without wildcards
                .limit(1)
                .execute()
            )
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
    try:
        logger.info(f"Auth request: mode={mode}, email={data.email}")
    except Exception:
        pass

    if mode not in {"login", "signup"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'login' or 'signup'.")

    public_client, admin_client, using_service = _build_supabase_clients()

    try:
        if mode == "login":
            # Email already normalized by validator
            res = public_client.auth.sign_in_with_password({
                "email": str(data.email),
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
            normalized_email = str(data.email)  # already normalized by validator

            # Pre-check for existing email in auth.users and profiles
            exists = _check_email_exists(admin_client, public_client, normalized_email)
            if exists.get("in_users") or exists.get("in_profiles"):
                raise HTTPException(
                    status_code=409,
                    detail="Email already registered. Please log in instead.",
                )

            payload = {
                "email": normalized_email,
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
    return {"route": _path or "/", "message": "FastAPI index2 alive"}

