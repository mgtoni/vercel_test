import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response

from ..models import AuthData, ProfileReq
from ..utils.core_supabase import build_supabase_public, admin_get_user_by_email_rest, fetch_profile_admin_sdk
from ..utils.crypto_utils import decrypt_auth_payload, aesgcm_encrypt_profile, mask_email_for_log
from ..utils.common import normalize_email
from ..utils.user_content import fetch_pdfs_from_manifest

router = APIRouter()
logger = logging.getLogger("api3.routes.user")


@router.get("/")
async def root():
    return {"message": "FastAPI index3 root alive"}


@router.post("/auth")
async def auth(data: AuthData, response: Response):
    mode = (data.mode or "").lower().strip()
    decrypted = decrypt_auth_payload(data.enc) if getattr(data, "enc", None) else None
    if getattr(data, "enc", None) and decrypted is None:
        raise HTTPException(status_code=400, detail="Invalid encrypted payload")
    email = normalize_email((decrypted or {}).get("email") or (data.email or ""))
    password = (decrypted or {}).get("password") or data.password or ""
    first_name = (decrypted or {}).get("first_name") or data.first_name
    last_name = (decrypted or {}).get("last_name") or data.last_name
    return_key_b64 = (decrypted or {}).get("rtk") or None
    try:
        logger.info(f"Auth request: mode={mode}, email={mask_email_for_log(email)}")
    except Exception:
        pass

    if mode not in {"login", "signup"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'login' or 'signup'.")

    try:
        public_client, service_key, supabase_url = build_supabase_public()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        if mode == "login":
            res = public_client.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
            user = getattr(res, "user", None)
            session = getattr(res, "session", None)
            profile = None
            try:
                uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
                uemail = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
                profile = fetch_profile_admin_sdk(supabase_url, service_key, user_id=uid, email=uemail)
            except Exception as e:
                logger.info(f"Profile enrichment skipped: {e}")

            user_meta_name = None
            meta_dict = {}
            try:
                if isinstance(user, dict):
                    meta_dict = (user.get("user_metadata") or {})
                    user_meta_name = meta_dict.get("name") or (" ".join([
                        (meta_dict.get("first_name") or "").strip(),
                        (meta_dict.get("last_name") or "").strip(),
                    ])).strip()
                else:
                    um = getattr(user, "user_metadata", None)
                    if isinstance(um, dict):
                        meta_dict = um
                        user_meta_name = um.get("name") or (" ".join([
                            (um.get("first_name") or "").strip(),
                            (um.get("last_name") or "").strip(),
                        ])).strip()
            except Exception:
                user_meta_name = None
            if user_meta_name and isinstance(meta_dict, dict) and "name" not in meta_dict:
                meta_dict["name"] = user_meta_name
            fn = (profile or {}).get("first_name") or (meta_dict or {}).get("first_name") or None
            ln = (profile or {}).get("last_name") or (meta_dict or {}).get("last_name") or None
            full_name = None
            if (profile or {}).get("full_name"):
                full_name = (profile or {}).get("full_name")
            elif (meta_dict or {}).get("name"):
                full_name = (meta_dict or {}).get("name")
            else:
                full_name = (f"{(fn or '').strip()} {(ln or '').strip()}").strip()

            pii = {
                "first_name": fn,
                "last_name": ln,
                "name": full_name,
                "email": getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None),
            }
            enc_blob = aesgcm_encrypt_profile(return_key_b64, pii)
            try:
                if session and getattr(session, "access_token", None):
                    response.set_cookie(
                        key="sb_access_token",
                        value=getattr(session, "access_token"),
                        httponly=True,
                        secure=True,
                        samesite="lax",
                        path="/",
                    )
            except Exception:
                pass
            return {
                "mode": mode,
                "user": {
                    "id": getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None),
                } if user else None,
                "session": {
                    "access_token": getattr(session, "access_token", None),
                    "token_type": getattr(session, "token_type", None),
                    "expires_in": getattr(session, "expires_in", None),
                } if session else None,
                **({"enc_profile": enc_blob["enc_profile"], "iv": enc_blob["iv"], "alg": enc_blob.get("alg", "AES-GCM")} if enc_blob else {}),
                "message": "Login successful" if session else "Login response received",
            }
        else:
            if service_key and admin_get_user_by_email_rest(supabase_url, service_key, email):
                raise HTTPException(
                    status_code=409,
                    detail="Email already registered. Please log in instead.",
                )

            if not (first_name and str(first_name).strip()) or not (last_name and str(last_name).strip()):
                raise HTTPException(status_code=400, detail="first_name and last_name are required for signup")

            payload = {"email": email, "password": password}
            metadata = {
                "first_name": str(first_name).strip(),
                "last_name": str(last_name).strip(),
                "name": f"{str(first_name).strip()} {str(last_name).strip()}".strip(),
            }
            payload["options"] = {"data": metadata}

            res = public_client.auth.sign_up(payload)
            user = getattr(res, "user", None)
            session = getattr(res, "session", None)
            try:
                if service_key and user:
                    from supabase import create_client as _create_client
                    admin_client = _create_client(supabase_url, service_key)
                    uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
                    profile_payload = {
                        "id": uid,
                        "first_name": str(first_name).strip(),
                        "last_name": str(last_name).strip(),
                        "full_name": (f"{str(first_name).strip()} {str(last_name).strip()}").strip(),
                    }
                    try:
                        admin_client.table("profiles").upsert(profile_payload).execute()
                    except Exception:
                        try:
                            admin_client.table("profiles").upsert({
                                "id": uid,
                                "full_name": profile_payload["full_name"],
                            }).execute()
                        except Exception as e2:
                            logger.info(f"Profiles upsert failed: {e2}")
            except Exception as e:
                logger.info(f"Profiles creation skipped: {e}")
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


@router.post("/")
async def auth_root(data: AuthData, response: Response):
    return await auth(data, response)


@router.post("/{_path:path}")
async def auth_any_path(_path: str, data: AuthData, response: Response):
    # Avoid intercepting admin endpoints
    try:
        if (_path or "").strip().lower().startswith("admin"):
            raise HTTPException(status_code=404, detail="Not found")
    except Exception:
        pass
    return await auth(data, response)


@router.get("/{_path:path}")
async def get_any_path(_path: str):
    return {"route": _path or "/", "message": "FastAPI index3 alive"}


@router.post("/profile")
async def get_profile(req: ProfileReq, request: Request):
    try:
        token = request.cookies.get("sb_access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        public_client, service_key, supabase_url = build_supabase_public()
        user_res = public_client.auth.get_user(token)
        user = getattr(user_res, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")
        uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
        uemail = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
        profile = fetch_profile_admin_sdk(supabase_url, service_key, user_id=uid, email=uemail)
        meta_dict = {}
        try:
            if isinstance(user, dict):
                meta_dict = (user.get("user_metadata") or {})
            else:
                um = getattr(user, "user_metadata", None)
                if isinstance(um, dict):
                    meta_dict = um
        except Exception:
            meta_dict = {}
        fn = (profile or {}).get("first_name") or (meta_dict or {}).get("first_name") or None
        ln = (profile or {}).get("last_name") or (meta_dict or {}).get("last_name") or None
        full_name = None
        if (profile or {}).get("full_name"):
            full_name = (profile or {}).get("full_name")
        elif (meta_dict or {}).get("name"):
            full_name = (meta_dict or {}).get("name")
        else:
            full_name = (f"{(fn or '').strip()} {(ln or '').strip()}").strip()
        pii = {"first_name": fn, "last_name": ln, "name": full_name, "email": uemail}
        enc_blob = aesgcm_encrypt_profile(req.rtk, pii)
        if not enc_blob:
            raise HTTPException(status_code=400, detail="Encryption unavailable")
        return {"enc_profile": enc_blob["enc_profile"], "iv": enc_blob["iv"], "alg": enc_blob.get("alg", "AES-GCM")}
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"/profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch profile")


@router.get("/pdfs")
async def list_pdfs(group: str, score: Optional[int] = None, limit: int = 10):
    try:
        limit = max(1, min(int(limit or 10), 100))
    except Exception:
        limit = 10
    try:
        items = fetch_pdfs_from_manifest(group=group, score=score, limit=limit)
        return {"items": items}
    except Exception as e:
        logger.info(f"/pdfs manifest error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch PDFs from manifest")
