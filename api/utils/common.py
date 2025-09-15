def normalize_email(email: str) -> str:
    try:
        return (email or "").strip().lower()
    except Exception:
        return email

