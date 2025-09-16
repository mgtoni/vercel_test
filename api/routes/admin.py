import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form

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


@router.post("/upload")
async def admin_upload_pdf(
    request: Request,
    bucket: str = Form(...),
    dest_path: str = Form(""),
    upsert: bool = Form(True),
    group_key: str | None = Form(None),
    label: str | None = Form(None),
    order_index: int | None = Form(None),
    is_default: bool | None = Form(None),
    score_min: int | None = Form(None),
    score_max: int | None = Form(None),
    active: bool | None = Form(True),
    file: UploadFile = File(...),
):
    """Upload a PDF to a Supabase Storage bucket and optionally insert a manifest row.

    - bucket: storage bucket name
    - dest_path: destination path or prefix in bucket; if ends with '/', the filename is appended
    - upsert: whether to overwrite existing object
    - group_key, label, order_index, is_default, score_min, score_max, active: if provided, creates a row in pdf_assets
    """
    _ = require_admin(request)
    try:
        from supabase import create_client as _create_client
        _public, service_key, supabase_url = build_supabase_public()
        admin = _create_client(supabase_url, service_key)

        # Normalize destination path
        orig_name = file.filename or "upload.pdf"
        safe_name = orig_name.split("/")[-1]
        dp = (dest_path or "").strip()
        if dp.endswith("/") or dp == "":
            final_path = (dp + safe_name).lstrip("/")
        else:
            final_path = dp.lstrip("/")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        options = {"content-type": file.content_type or "application/pdf", "upsert": bool(upsert)}
        # Upload to storage
        admin.storage.from_(bucket).upload(final_path, content, options)

        # Optional manifest insert
        inserted = None
        if group_key:
            payload = {
                "group_key": group_key,
                "bucket": bucket,
                "path": final_path,
                "label": label or safe_name,
                "order_index": order_index if order_index is not None else 0,
                "is_default": bool(is_default) if is_default is not None else False,
                "score_min": score_min,
                "score_max": score_max,
                "active": True if active is None else bool(active),
            }
            res = admin.table("pdf_assets").insert(payload).execute()
            data = getattr(res, "data", None) or []
            inserted = data[0] if data else None

        # Signed URL for immediate preview
        try:
            from ..utils.core_supabase import create_signed_storage_url
            signed_url = create_signed_storage_url(supabase_url, service_key, bucket, final_path, 1800)
        except Exception:
            signed_url = None

        return {
            "bucket": bucket,
            "path": final_path,
            "content_type": options["content-type"],
            "upsert": bool(upsert),
            "manifest": inserted,
            "signed_url": signed_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"admin_upload_pdf error: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload PDF")
