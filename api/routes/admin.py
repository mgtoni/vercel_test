import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request

from ..models import PdfAssetCreate, PdfAssetUpdate
from ..utils.admin_checks import require_admin
from ..utils.core_supabase import build_supabase_public

router = APIRouter(prefix="/admin")
logger = logging.getLogger("api3.routes.admin")


@router.get("/me")
async def admin_me(request: Request):
    email = require_admin(request)
    return {"email": email, "is_admin": True}


@router.get("/pdfs")
async def admin_list_pdfs(request: Request, group: Optional[str] = None, limit: int = 50, offset: int = 0):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        q = (
            admin.table("pdf_assets")
            .select("id,group_key,bucket,path,label,order_index,is_default,score_min,score_max,active,created_at,updated_at")
            .order("group_key", desc=False)
            .order("order_index", desc=False)
        )
        if group:
            q = q.eq("group_key", group)
        if offset:
            q = q.range(offset, offset + max(0, int(limit)) - 1)
        else:
            q = q.limit(max(1, min(int(limit or 50), 200)))
        res = q.execute()
        items = getattr(res, "data", None) or []
        return {"items": items}
    except Exception as e:
        logger.info(f"admin_list_pdfs error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list pdf_assets")


@router.post("/pdfs")
async def admin_create_pdf(request: Request, body: PdfAssetCreate):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        payload = body.dict()
        res = admin.table("pdf_assets").insert(payload).execute()
        data = getattr(res, "data", None) or []
        return {"item": data[0] if data else None}
    except Exception as e:
        logger.info(f"admin_create_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create pdf_asset")


@router.put("/pdfs/{item_id}")
async def admin_update_pdf(item_id: str, request: Request, body: PdfAssetUpdate):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        update = {k: v for k, v in body.dict().items() if v is not None}
        if not update:
            return {"item": None}
        res = admin.table("pdf_assets").update(update).eq("id", item_id).execute()
        data = getattr(res, "data", None) or []
        return {"item": data[0] if data else None}
    except Exception as e:
        logger.info(f"admin_update_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update pdf_asset")


@router.delete("/pdfs/{item_id}")
async def admin_delete_pdf(item_id: str, request: Request):
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)
        res = admin.table("pdf_assets").delete().eq("id", item_id).execute()
        data = getattr(res, "data", None) or []
        return {"deleted": len(data)}
    except Exception as e:
        logger.info(f"admin_delete_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete pdf_asset")

