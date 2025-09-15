import os
import json as _json
import base64 as _b64
import logging
from typing import Optional, Dict

logger = logging.getLogger("api3.crypto")

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    serialization = None
    padding = None
    hashes = None
    default_backend = None
    AESGCM = None


def load_private_key():
    """Load RSA private key from env var `AUTH_PRIVATE_KEY_PEM` or `api/keys/private_key.pem`.

    Returns a cryptography private key object, or None if unavailable.
    """
    if serialization is None:
        return None
    pem = os.getenv("AUTH_PRIVATE_KEY_PEM")
    if pem:
        try:
            if "\\n" in pem and "\n" not in pem:
                pem = pem.replace("\\n", "\n")
            key = serialization.load_pem_private_key(
                pem.encode("utf-8"), password=None, backend=default_backend()
            )
            return key
        except Exception:
            pass
    file_path = os.path.join(os.path.dirname(__file__), "..", "keys", "private_key.pem")
    try:
        file_path = os.path.normpath(file_path)
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                key = serialization.load_pem_private_key(
                    f.read(), password=None, backend=default_backend()
                )
                return key
    except Exception:
        pass
    return None


def decrypt_auth_payload(enc_b64: str) -> Optional[Dict]:
    """Decrypt base64-encoded RSA-OAEP (SHA-256) payload containing JSON.

    Expected JSON shape: { email, password, first_name?, last_name?, rtk? }
    Returns dict or None if decryption fails or key missing.
    """
    try:
        if not enc_b64:
            return None
        priv = load_private_key()
        if priv is None:
            logger.warning("AUTH_PRIVATE_KEY not available; cannot decrypt 'enc' payload")
            return None
        ciphertext = _b64.b64decode(enc_b64)
        plaintext = priv.decrypt(
            ciphertext,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        data = _json.loads(plaintext.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception as e:
        logger.info(f"Decryption failed: {e}")
        return None


def mask_email_for_log(email: str) -> str:
    try:
        if not email:
            return ""
        parts = email.split("@", 1)
        user = parts[0]
        domain = parts[1] if len(parts) > 1 else ""
        first = (user[:1] or "*")
        last = (user[-1:] or "*")
        return f"{first}***{last}@{domain}" if domain else f"{first}***{last}"
    except Exception:
        return "***"


def aesgcm_encrypt_profile(return_key_b64: Optional[str], profile: Dict) -> Optional[Dict]:
    """Encrypt profile dict with AES-GCM using a base64 return key from client.

    Returns dict with 'enc_profile' (base64) and 'iv' (base64) or None.
    """
    try:
        if not return_key_b64 or AESGCM is None:
            return None
        key = _b64.b64decode(return_key_b64)
        if len(key) not in (16, 24, 32):
            return None
        aesgcm = AESGCM(key)
        iv = os.urandom(12)
        plaintext = _json.dumps(profile).encode("utf-8")
        ct = aesgcm.encrypt(iv, plaintext, associated_data=None)
        return {
            "enc_profile": _b64.b64encode(ct).decode("utf-8"),
            "iv": _b64.b64encode(iv).decode("utf-8"),
            "alg": "AES-GCM",
        }
    except Exception as e:
        logger.info(f"AES-GCM encrypt failed: {e}")
        return None
