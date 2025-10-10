import os
import json as _json
import logging
from typing import Optional, Dict
from urllib import request as _urlreq
from urllib import parse as _urlparse

logger = logging.getLogger("api3.supabase.core")

try:
    from supabase import create_client
except Exception:
    create_client = None


def build_supabase_public():
    """Create a Supabase client with anon or service key.

    Returns (public_client, service_key, supabase_url).
    """
    if create_client is None:
        raise RuntimeError("Supabase client not installed on server.")

    supabase_url = os.getenv("SUPABASE_URL") or ""
    anon_key = os.getenv("SUPABASE_ANON_KEY") or ""
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""

    if not supabase_url or not (anon_key or service_key):
        raise RuntimeError("Supabase environment not configured.")

    public_client = create_client(supabase_url, anon_key or service_key)
    return public_client, service_key, supabase_url


def admin_get_user_by_email_rest(supabase_url: str, service_key: str, email: str) -> bool:
    """Check auth.users for a matching email via GoTrue Admin REST.

    Returns True if a case-insensitive match is found; False otherwise.
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
        if isinstance(data, list):
            return any(((u.get("email") or "").lower() == email.lower()) for u in data)
        if isinstance(data, dict):
            arr = data.get("users") or data.get("data") or []
            if isinstance(arr, list):
                return any(((getattr(u, "email", None) or u.get("email") or "").lower() == email.lower()) for u in arr)
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


def fetch_profile_admin_sdk(
    supabase_url: str,
    service_key: str,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[Dict]:
    """Fetch a single profile using the Supabase Python client with service role key."""
    if not service_key or create_client is None:
        return None
    try:
        admin_client = create_client(supabase_url, service_key)
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
            except Exception:
                continue
    except Exception as e:
        logger.info(f"Profile fetch (SDK) failed: {e}")
    return None


def create_signed_storage_url(supabase_url: str, service_key: str, bucket: str, path: str, expires_in: int = 1800) -> Optional[str]:
    """Create a time-limited signed URL for a storage object."""
    if not service_key or create_client is None:
        return None


def create_signed_upload_url(supabase_url: str, service_key: str, bucket: str, path: str) -> Optional[Dict[str, str]]:
    """Create a signed upload URL for direct-from-browser upload to Storage.

    Returns dict { 'signed_url': str, 'token': str } or None on failure.
    """
    if not service_key or create_client is None:
        return None
    try:
        admin_client = create_client(supabase_url, service_key)
        res = admin_client.storage.from_(bucket).create_signed_upload_url(path)
        # SDK may return dict or object
        signed_url = getattr(res, "signed_url", None) or (res.get("signed_url") if isinstance(res, dict) else None)
        token = getattr(res, "token", None) or (res.get("token") if isinstance(res, dict) else None)
        if signed_url and token:
            absolute_url = signed_url
            if isinstance(absolute_url, str) and absolute_url.startswith("/"):
                absolute_url = f"{supabase_url.rstrip('/')}{absolute_url}"
            return {"signed_url": absolute_url, "token": token}
    except Exception as e:
        logger.info(f"Signed upload URL generation failed for {bucket}/{path}: {e}")
    return None
    try:
        admin_client = create_client(supabase_url, service_key)
        res = admin_client.storage.from_(bucket).create_signed_url(path, expires_in)
        url = getattr(res, "signed_url", None) or (res.get("signed_url") if isinstance(res, dict) else None)
        return url
    except Exception as e:
        logger.info(f"Signed URL generation failed for {bucket}/{path}: {e}")
        return None
