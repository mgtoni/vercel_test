import os
import json as _json
import logging
from typing import Optional, Dict, List
from urllib import request as _urlreq
from urllib import parse as _urlparse

logger = logging.getLogger("api3.supabase")

try:
    from supabase import create_client
except Exception:
    create_client = None


def build_supabase_public():
    """Create a public Supabase client and return (client, service_key, supabase_url).
    service_key is returned to enable admin REST calls when available; may be empty string.
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
    """Fetch a single profile using the Supabase Python client with service role key.

    This avoids URL quirks with PostgREST and leverages the SDK.
    """
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


def build_public_storage_url(supabase_url: str, bucket: str, path: str) -> str:
    base = supabase_url.rstrip("/")
    path = path.lstrip("/")
    bucket = bucket.strip("/")
    return f"{base}/storage/v1/object/public/{bucket}/{path}"


def create_signed_storage_url(supabase_url: str, service_key: str, bucket: str, path: str, expires_in: int = 3600) -> Optional[str]:
    """Create a time-limited signed URL for a storage object.

    Requires service role key. Returns URL or None on failure.
    """
    if not service_key or create_client is None:
        return None
    try:
        admin_client = create_client(supabase_url, service_key)
        res = admin_client.storage.from_(bucket).create_signed_url(path, expires_in)
        url = getattr(res, "signed_url", None) or (res.get("signed_url") if isinstance(res, dict) else None)
        return url
    except Exception as e:
        logger.info(f"Signed URL generation failed for {bucket}/{path}: {e}")
        return None


def get_pdf_urls_from_storage(
    *,
    bucket: str,
    path1: str,
    path2: str,
    path3: str,
    public: bool,
    expires_in: int = 3600,
) -> Dict[str, Optional[str]]:
    """Resolve three PDF URLs from Supabase Storage, using public or signed URLs.

    Reads Supabase env via build_supabase_public().
    """
    public_client, service_key, supabase_url = build_supabase_public()
    if public:
        return {
            "pdf1": build_public_storage_url(supabase_url, bucket, path1),
            "pdf2": build_public_storage_url(supabase_url, bucket, path2),
            "pdf3": build_public_storage_url(supabase_url, bucket, path3),
        }
    else:
        return {
            "pdf1": create_signed_storage_url(supabase_url, service_key, bucket, path1, expires_in),
            "pdf2": create_signed_storage_url(supabase_url, service_key, bucket, path2, expires_in),
            "pdf3": create_signed_storage_url(supabase_url, service_key, bucket, path3, expires_in),
        }


def fetch_pdfs_from_manifest(
    *,
    group: str,
    score: Optional[int] = None,
    limit: int = 10,
    expires_in: int = 1800,
) -> List[Dict]:
    """Query `pdf_assets` manifest by group (and optional score), return signed URLs.

    - When `score` is None: returns items where is_default = true
    - When `score` is provided: returns items where
        (score_min is null or score_min <= score) AND (score_max is null or score <= score_max)
    - Only items where active = true
    - Ordered by order_index asc
    """
    if not group or create_client is None:
        return []
    try:
        public_client, service_key, supabase_url = build_supabase_public()
        if not service_key:
            return []
        admin = create_client(supabase_url, service_key)

        q = (
            admin
            .table("pdf_assets")
            .select("id,bucket,path,label,order_index,is_default,score_min,score_max,active")
            .eq("group_key", group)
            .eq("active", True)
            .order("order_index", desc=False)
        )

        if score is None:
            q = q.eq("is_default", True)
        else:
            # score_min <= score (or null) AND score <= score_max (or null)
            q = q.or_(f"score_min.is.null,score_min.lte.{score}")
            q = q.or_(f"score_max.is.null,score_max.gte.{score}")

        if limit and limit > 0:
            q = q.limit(limit)

        res = q.execute()
        items = getattr(res, "data", None) or []
        out: List[Dict] = []
        for it in items:
            b = it.get("bucket")
            p = it.get("path")
            url = create_signed_storage_url(supabase_url, service_key, b, p, expires_in)
            if not url:
                continue
            out.append({
                "id": it.get("id"),
                "label": it.get("label") or p,
                "bucket": b,
                "path": p,
                "signed_url": url,
                "order_index": it.get("order_index") or 0,
                "is_default": bool(it.get("is_default")),
                "score_min": it.get("score_min"),
                "score_max": it.get("score_max"),
            })
        return out
    except Exception as e:
        logger.info(f"fetch_pdfs_from_manifest failed: {e}")
        return []


def check_email_exists_rest(public_client, supabase_url: str, service_key: str, email: str) -> Dict:
    """Deprecated compatibility helper; now only checks auth.users via admin REST when possible."""
    result = {"in_users": False, "in_profiles": False}
    try:
        if service_key:
            result["in_users"] = admin_get_user_by_email_rest(supabase_url, service_key, email)
    except Exception as e:
        logger.info(f"Admin REST check unavailable: {e}")
    return result
