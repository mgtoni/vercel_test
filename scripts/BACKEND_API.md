# Backend Overview and API Endpoints (FastAPI)

This backend is implemented with FastAPI inside `api/index.py`. Vercel rewrites route all `/api` traffic to this single function, which exposes multiple GET/POST handlers.

## Libraries Used
- `fastapi`: Web framework to declare routes and Pydantic models.
- `pydantic`: Request body validation and parsing.
- `supabase` (Python client v2): Used for login/signup and reading/writing to the `profiles` table.
- `logging`: Request and error logging via a simple middleware.
- `urllib.request` / `urllib.parse`: Used for GoTrue Admin REST calls (email checks) when the service role key is available.

## Request Logging Middleware
`@app.middleware("http")` logs incoming method+path and the resulting status code. Unhandled exceptions are logged before being re-raised.

## Environment
- `SUPABASE_URL`: Base URL of your Supabase project.
- `SUPABASE_ANON_KEY`: Public client key.
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key (optional, enables admin-level checks and profile upserts on signup).

## Endpoints

### GET `/`
- Liveness check for the function root.
- Response: `{ "message": "FastAPI index3 root alive" }`.

### POST `/auth`
Unified login and signup endpoint.
- Request body (Pydantic model `AuthData`):
  - `mode`: `'login' | 'signup'`
  - `email`: string
  - `password`: string
  - `first_name?`, `last_name?`: required for signup

- Behavior:
  - `login`:
    - Calls `supabase.auth.sign_in_with_password({ email, password })`.
    - Attempts to enrich response using `profiles` via `_fetch_profile_admin_sdk` (if service role key available).
    - Falls back to `user_metadata` name if present.
    - Returns `user`, `session`, and optional `profile`.
  - `signup`:
    - Normalizes and pre-checks the email for duplicates via `_check_email_exists_rest` (auth.users and `profiles` table).
    - Requires `first_name` and `last_name`.
    - Calls `supabase.auth.sign_up(payload)` attaching metadata (`first_name`, `last_name`, `name`).
    - If service role key is present, upserts a row into `public.profiles` for the new user.

- Errors and status codes:
  - 400 Bad Request for invalid mode or other client-side issues (e.g., missing names in signup).
  - 409 Conflict if email already exists in auth or profiles.

### POST `/` (fallback)
- For platforms that rewrite unknown POST subpaths to the function root.
- Forwards to the same logic as `/auth` to keep behavior consistent.

### POST `/{_path:path}` (catch-all)
- Accepts any POST under `/api/...` and forwards to `auth`. This allows clients to call `/api/login` or `/api/signup` and reach the same handler.

### GET `/{_path:path}` (catch-all)
- Returns a small info object to confirm routing without requiring a request body:
  - `{ "route": "<requestedPath>", "message": "FastAPI index3 alive" }`.

## How GET vs POST Works Here
- GET routes return liveness/routing info. They do not accept a body.
- POST routes accept JSON bodies. The client must set `Content-Type: application/json` and send a JSON-encoded object. FastAPI/Pydantic validates and parses it into the declared model (`FormData` or `AuthData`).
- Responses are JSON objects; the frontend parses them and uses the data to update UI state (e.g., `localStorage` and navigation).

## Request/Response Examples

Login request:
```http
POST /api/auth
Content-Type: application/json

{
  "mode": "login",
  "email": "ada@example.com",
  "password": "secret"
}
```

Successful login response (shape simplified):
```json
{
  "mode": "login",
  "user": {
    "id": "...",
    "email": "ada@example.com",
    "user_metadata": { "name": "Ada Lovelace", "first_name": "Ada", "last_name": "Lovelace" }
  },
  "session": {
    "access_token": "...",
    "token_type": "bearer",
    "expires_in": 3600
  },
  "profile": { "id": "...", "first_name": "Ada", "last_name": "Lovelace", "full_name": "Ada Lovelace" },
  "message": "Login successful"
}
```

Signup request:
```http
POST /api/auth
Content-Type: application/json

{
  "mode": "signup",
  "email": "ada@example.com",
  "password": "secret",
  "first_name": "Ada",
  "last_name": "Lovelace"
}
```

Duplicate email response:
```json
{
  "detail": "Email already registered. Please log in instead."
}
```

## Notes on Vercel Rewrites
Because `vercel.json` rewrites both `/api` and `/api/:path*` to the same function, the catch-all routes in `api/index.py` ensure POSTs and GETs to any subpath are correctly handled. This makes local development and production routing behave consistently.

