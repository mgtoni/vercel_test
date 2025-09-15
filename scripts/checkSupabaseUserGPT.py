import os
from supabase import create_client, Client

# --- Fill these in with your own values ---
SUPABASE_URL = "https://rmlnxoulfoegdyyppvfr.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJtbG54b3VsZm9lZ2R5eXBwdmZyIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NzMzMzM1MCwiZXhwIjoyMDcyOTA5MzUwfQ.LIxLsmJ4IrRJl_jd_HdSHpdioxcQ4vL7RAzC5b9yfF0"
EMAIL_TO_CHECK = "toni.mares@yahoo.com"
# --------------------------------------------------

def main():
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    try:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        admin = getattr(client.auth, "admin", None)
        print("********")
        print(dir(admin))
        print("£££££££££££££")
        for u in admin.list_users():
            print(dir(u))
            print(u.email)

        matching = [u for u in admin.list_users() if u.email.lower() == EMAIL_TO_CHECK.lower()]

        if matching:
            print(f"✅ User with email {EMAIL_TO_CHECK} exists.")
        else:
            print(f"❌ No user found with email {EMAIL_TO_CHECK}.")
    except Exception as e:
        print("Error checking user:", e)

if __name__ == "__main__":
    main()
