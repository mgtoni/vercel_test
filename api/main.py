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

class FormData(BaseModel):
    name: str
    email: str

@app.post("/submit")
async def submit_form(data: FormData):
    print(f"Received data: {data}")
    return {"message": "Data received successfully"}


class AuthData(BaseModel):
    mode: str  # 'login' or 'signup'
    email: str
    password: str
    name: Optional[str] = None


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
            payload = {
                "email": data.email,
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
        # Bubble up as a 400 for auth failures
        raise HTTPException(status_code=400, detail=str(e))


# Fallback root handler to support platform rewrites that drop subpaths
@app.post("/")
async def auth_root(data: AuthData):
    return await auth(data)


# Catch-all POST to support rewrites preserving subpaths
@app.post("/{_path:path}")
async def auth_any_path(_path: str, data: AuthData):
    return await auth(data)
