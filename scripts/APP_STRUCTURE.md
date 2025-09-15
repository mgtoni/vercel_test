# App Structure Overview

This project consists of a React frontend (bundled with Vite) and a Python backend (FastAPI) deployed behind Vercel rewrites. The two layers communicate over simple JSON HTTP requests routed under `/api`.

## High-Level Layout

- `frontend/`: Vite + React SPA.
  - Entrypoint HTML at `frontend/index.html` loads `src/index.jsx` → `src/App.jsx`.
  - Client-side routing via `react-router-dom` to pages: `/`, `/form`, `/profile`.
  - Network calls use `fetch` to hit backend endpoints under `/api`.

- `api/`: FastAPI application for server-side endpoints.
  - Main function file: `api/index.py`.
  - Dependencies: `api/requirements.txt` (FastAPI, supabase>=2.4.0, email-validator).
  - Exposes endpoints for liveness, a demo submit handler, and a unified auth flow.

- `scripts/`: Helper files for backend data setup and documentation.
  - `scripts/setup_auth_profiles.sql`: Creates a `public.profiles` table, policies, and triggers in Supabase.

- Root config files
  - `vercel.json`: Controls build commands and URL rewrites for frontend and backend.
  - `package.json`: Root Node constraints (Node >= 18).

## How Routing Works (Vercel)

- Frontend build
  - `installCommand`: `npm install --prefix frontend`
  - `buildCommand`: `npm run build --prefix frontend`
  - `outputDirectory`: `frontend/dist`

- Rewrites in `vercel.json`:
  - `{"source": "/api", "destination": "/api/index"}`
  - `{"source": "/api/:path*", "destination": "/api/index"}`
  - `{"source": "/:path*", "destination": "/index.html"}`

Effectively:
- Any request starting with `/api` is routed to the FastAPI function in `api/index.py`.
- All other routes serve the SPA’s `index.html` so React Router can handle client-side navigation.

## How Frontend and Backend Interact

- The React app issues HTTP requests with `fetch` to `/api/...`.
- The FastAPI backend parses JSON bodies into Pydantic models and returns JSON responses.
- For authentication:
  - Frontend posts to `/api/auth` with `{ mode, email, password, ... }`.
  - Backend uses the Supabase Python client to log in or sign up, optionally enriching profile data from the `profiles` table.
  - On successful login, the frontend stores a minimal profile in `localStorage` and navigates to `/profile`.

## Data Model Touchpoints

- Supabase Auth (`auth.users`): user accounts managed by Supabase GoTrue.
- `public.profiles` table: stores first/last name, email, and a computed `full_name`. The SQL in `scripts/setup_auth_profiles.sql` creates the table, RLS policies, triggers to sync metadata from auth, and helper functions.

## Key Files to Explore

- Frontend
  - `frontend/src/App.jsx`
  - `frontend/src/pages/Home.jsx`
  - `frontend/src/pages/FormPage.jsx`
  - `frontend/src/components/Form.jsx`
  - `frontend/src/pages/Profile.jsx`

- Backend
  - `api/index.py`
  - `api/requirements.txt`
  - `vercel.json`

