# Python, Libraries, and Supabase Helpers

This backend uses FastAPI with the Supabase Python client (v2) to implement a unified auth flow and basic profile enrichment. Below is an explanation of the main libraries and the four Supabase-related helper functions used in `api/index.py`.

## Python Libraries in Context
- `fastapi`: Declares the web app and HTTP routes. Each route is an async function returning JSON. Middlewares can log requests and handle cross-cutting concerns.
- `pydantic`: Defines request models (`FormData`, `AuthData`). FastAPI validates inputs against these models and gives you typed Python objects.
- `supabase` (Python client v2): Provides `create_client(url, key)` and SDK methods:
  - `client.auth.sign_in_with_password({ email, password })`
  - `client.auth.sign_up(payload)` where `payload.options.data` carries user metadata
  - `client.table("profiles").select(...).eq/ilike(...).limit(...).execute()` for PostgREST-backed queries
- `logging`: Logs events for observability; the middleware logs each request and result status.
- `urllib.request` and `urllib.parse`: Used for direct HTTP calls to the Supabase GoTrue Admin REST API when the service role key is present.

## Environment Variables
- `SUPABASE_URL`: Project URL, e.g. `https://xyzcompany.supabase.co`
- `SUPABASE_ANON_KEY`: Public (anon) API key
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key; optional but enables admin operations (e.g., listing users, upserting profiles without RLS restrictions)

## The Four Supabase Helper Functions

All reside in `api/index.py` and are used by the `/auth` endpoint.

1) `_build_supabase_public() -> Tuple[client, service_key, supabase_url]`
- Purpose: Centralizes initialization of the Supabase SDK client and returns the service role key and URL alongside it.
- Logic:
  - Reads `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
  - If both URL and at least one key are present, initializes a client using `anon_key or service_key`.
  - Returns `(public_client, service_key, supabase_url)`.
- Why it matters: A single place to handle config errors and share the URL and service key with other helpers that may need admin functionality.

2) `_admin_get_user_by_email_rest(supabase_url: str, service_key: str, email: str) -> bool`
- Purpose: Check if an email exists in `auth.users` using GoTrue Admin REST endpoints.
- Logic:
  - Requires `service_key`. If missing, returns `False` early.
  - Constructs `GET {SUPABASE_URL}/auth/v1/admin/users?email=<email>` and attempts to parse the JSON response for a match.
  - If the direct email filter isn’t supported, falls back to `GET .../users?page=1&per_page=200` and scans results client-side.
  - Returns `True` if a case-insensitive email match is found.
- Why it matters: Avoids duplicate signups and lets the server verify whether a user already exists without exposing admin keys to the client.

3) `_fetch_profile_admin_sdk(supabase_url: str, service_key: str, user_id?: str, email?: str) -> Optional[dict]`
- Purpose: Retrieve a single profile row using the Supabase SDK authenticated with the service role key.
- Logic:
  - Requires `service_key` (and the Python client available). Otherwise returns `None`.
  - Creates `admin_client = create_client(supabase_url, service_key)`.
  - Attempts to select profile fields with progressively simpler selectors to support different schemas:
    - `id,first_name,last_name,full_name` → then `id,full_name` → then `id,name`
  - Filters by `id` if provided, else by `email` if provided.
  - Returns a normalized dict: `{ id, first_name?, last_name?, full_name? }` or `None`.
- Why it matters: Enriches login responses with profile names when available, even if the schema differs slightly between environments.

4) `_check_email_exists_rest(public_client, supabase_url: str, service_key: str, email: str) -> dict`
- Purpose: Determine whether an email is already present in either `auth.users` or `public.profiles`.
- Logic:
  - Initializes a result dict: `{ "in_users": False, "in_profiles": False }`.
  - If `service_key` is present, calls `_admin_get_user_by_email_rest(...)` to populate `in_users`.
  - Queries `public.profiles` using the public client; prefers case-insensitive `ilike("email", email)` when available, otherwise `eq("email", email)`; sets `in_profiles` accordingly.
  - Returns the combined existence result.
- Why it matters: Used during signup to prevent duplicate registrations and provide a clean 409 Conflict error when an email is already registered.

## Putting It Together in `/auth`
- Login flow (`mode=login`): Uses `public_client.auth.sign_in_with_password`. If successful, tries to fetch a profile via `_fetch_profile_admin_sdk` to include first/last names in the response. Falls back to `user_metadata` name if present.
- Signup flow (`mode=signup`): Normalizes email, ensures `first_name` and `last_name` are provided, checks duplicates with `_check_email_exists_rest`, and then calls `auth.sign_up` with metadata. If possible, upserts a corresponding row into `public.profiles` via an admin client.

## Profiles Table and SQL Setup
- See `scripts/setup_auth_profiles.sql` for an idempotent setup of a `public.profiles` table with RLS, triggers that mirror names from `auth.users` metadata, and a helper RPC to update names.

## Notes & Extensibility
- For larger apps, consider splitting helpers into separate modules, adding more granular error handling, and introducing typed response models.
- If you need public read access to profiles (e.g., for a directory), add a controlled read policy in Supabase RLS or proxy reads through the backend.

