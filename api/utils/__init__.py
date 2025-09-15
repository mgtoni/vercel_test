"""Utility helpers used by the API routes.

Re-export common helpers for convenience.
"""

from .common import normalize_email
from .crypto_utils import (
    load_private_key,
    decrypt_auth_payload,
    aesgcm_encrypt_profile,
    mask_email_for_log,
)
from .supabase_utils import (
    build_supabase_public,
    admin_get_user_by_email_rest,
    fetch_profile_admin_sdk,
    check_email_exists_rest,
)

__all__ = [
    "normalize_email",
    "load_private_key",
    "decrypt_auth_payload",
    "aesgcm_encrypt_profile",
    "mask_email_for_log",
    "build_supabase_public",
    "admin_get_user_by_email_rest",
    "fetch_profile_admin_sdk",
    "check_email_exists_rest",
]

