import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

try:
    import bcrypt  # type: ignore
except Exception:  # pragma: no cover - optional dependency guard
    bcrypt = None  # type: ignore

from .core_supabase import build_supabase_public

logger = logging.getLogger("api3.admin_auth")

SESSION_COOKIE = "admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 12  # 12 hours
RESET_TTL_SECONDS = 60 * 10  # 10 minutes


def _get_secret() -> bytes:
    secret = os.getenv("ADMIN_SESSION_SECRET") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not secret:
        raise RuntimeError("Admin session secret not configured")
    return secret.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(body: str, password_hash: Optional[str], purpose: str) -> str:
    secret = _get_secret()
    payload = f"{body}|{purpose}|{password_hash or ''}".encode("utf-8")
    digest = hmac.new(secret, payload, hashlib.sha256).digest()
    return _b64url(digest)


def _generate_token(email: str, password_hash: Optional[str], ttl_seconds: int, purpose: str) -> str:
    payload = {
        "email": email,
        "exp": int(time.time()) + ttl_seconds,
        "nonce": secrets.token_urlsafe(12),
        "purpose": purpose,
    }
    body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = _b64url(body_bytes)
    signature = _sign(body, password_hash, purpose)
    return f"{body}.{signature}"


def _decode_payload(token: str) -> Optional[Dict[str, Any]]:
    try:
        body = token.split(".", 1)[0]
        data = json.loads(_b64url_decode(body))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.info(f"Failed to decode admin token payload: {exc}")
    return None


def _verify_token(token: str, password_hash: Optional[str], expected_purpose: str) -> Optional[Dict[str, Any]]:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    expected_sig = _sign(body, password_hash, expected_purpose)
    if not hmac.compare_digest(signature, expected_sig):
        return None
    try:
        payload_bytes = _b64url_decode(body)
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict):
            return None
    except Exception:
        return None
    if payload.get("purpose") != expected_purpose:
        return None
    exp = payload.get("exp")
    try:
        if int(exp) < int(time.time()):
            return None
    except Exception:
        return None
    return payload


def create_session_token(email: str, password_hash: str) -> str:
    return _generate_token(email, password_hash, SESSION_TTL_SECONDS, "session")


def verify_session_token(token: str, password_hash: str) -> Optional[Dict[str, Any]]:
    return _verify_token(token, password_hash, "session")


def decode_session_payload(token: str) -> Optional[Dict[str, Any]]:
    payload = _decode_payload(token)
    if payload and payload.get("purpose") == "session":
        return payload
    return None


def create_reset_token(email: str, password_hash: Optional[str]) -> str:
    return _generate_token(email, password_hash, RESET_TTL_SECONDS, "reset")


def decode_reset_payload(token: str) -> Optional[Dict[str, Any]]:
    payload = _decode_payload(token)
    if payload and payload.get("purpose") == "reset":
        return payload
    return None


def verify_reset_token(token: str, password_hash: Optional[str]) -> Optional[Dict[str, Any]]:
    return _verify_token(token, password_hash, "reset")


def hash_password(password: str) -> str:
    if bcrypt is None:
        raise RuntimeError("bcrypt library not installed. Install via 'pip install bcrypt'.")
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, stored_value: Optional[str]) -> Tuple[bool, bool]:
    if not stored_value:
        return False, False
    value = str(stored_value)
    try:
        if value.startswith("$2") and len(value) >= 4:
            if bcrypt is None:
                raise RuntimeError("bcrypt library not installed. Install via 'pip install bcrypt'.")
            matched = bcrypt.checkpw(password.encode("utf-8"), value.encode("utf-8"))
            return matched, True
        matched = hmac.compare_digest(password, value)
        return matched, False
    except ValueError:
        return False, False


RESET_FLAGS = (
    "force_password_change",
    "must_reset_password",
    "password_reset_required",
    "needs_password_reset",
    "requires_password_update",
)

RESET_TIMESTAMP_FIELDS = (
    "password_updated_at",
    "password_last_updated",
)


def as_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "y"}
    return False


def requires_password_change(row: Dict[str, Any], password_is_hashed: bool) -> bool:
    for key in RESET_FLAGS:
        if key in row and as_bool(row.get(key)):
            return True
    for key in RESET_TIMESTAMP_FIELDS:
        if key in row and not row.get(key):
            return True
    if not password_is_hashed:
        return True
    return False


def build_admin_client():
    try:
        from supabase import create_client as _create_client
    except Exception as exc:
        raise RuntimeError("Supabase client not installed") from exc

    public_client, service_key, supabase_url = build_supabase_public()
    if not service_key:
        raise RuntimeError("Supabase service role key required for admin operations")
    client = _create_client(supabase_url, service_key)
    return client


def fetch_admin_user(email: str) -> Optional[Dict[str, Any]]:
    try:
        client = build_admin_client()
        attempts = []
        if email:
            attempts.append(("eq", email))
            lowered = email.lower()
            if lowered != email:
                attempts.append(("eq", lowered))
            attempts.append(("ilike", email))
        for mode, value in attempts:
            query = client.table("admin_users").select("*").limit(1)
            if mode == "eq":
                query = query.eq("email", value)
            else:
                query = query.ilike("email", value)
            res = query.execute()
            data = getattr(res, "data", None)
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict) and data:
                return data
    except Exception as exc:
        logger.info(f"fetch_admin_user failed for {email}: {exc}")
    return None


def update_admin_user(email: str, updates: Dict[str, Any]) -> bool:
    try:
        client = build_admin_client()
        res = client.table("admin_users").update(updates).eq("email", email).execute()
        data = getattr(res, "data", None)
        if data is None:
            return True
        return bool(data)
    except Exception as exc:
        logger.info(f"update_admin_user failed for {email}: {exc}")
        return False


def build_password_update_payload(row: Dict[str, Any], new_password_hash: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"password_hash": new_password_hash}
    for key in RESET_FLAGS:
        if key in row:
            payload[key] = False
    for key in RESET_TIMESTAMP_FIELDS:
        if key in row:
            payload[key] = datetime.now(timezone.utc).isoformat()
    if "password" in row:
        payload["password"] = None
    if "password_temp" in row:
        payload["password_temp"] = None
    return payload
