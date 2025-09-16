import logging
from typing import Optional, Dict, List

from .core_supabase import build_supabase_public, create_signed_storage_url

logger = logging.getLogger("api3.user_content")


def fetch_pdfs_from_manifest(
    *,
    group: str,
    score: Optional[int] = None,
    limit: int = 10,
    expires_in: int = 1800,
) -> List[Dict]:
    """Query `pdf_assets` manifest by group (and optional score), return signed URLs."""
    from supabase import create_client as _create_client

    if not group:
        return []
    try:
        _public, service_key, supabase_url = build_supabase_public()
        if not service_key:
            return []
        admin = _create_client(supabase_url, service_key)

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

