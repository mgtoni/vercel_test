# Frontend Overview (Vite + React)

## Stack
- React + React Router (SPA)
- Vite for dev/build tooling (`frontend/vite.config.js`)
- Served by Vercel; all non-`/api` routes rewrite to the SPA (`index.html`).

## Entrypoints and Routing
- `frontend/index.html`: Static HTML shell with `<div id="root">`.
- `frontend/src/index.jsx`: Boots the React app into `#root`.
- `frontend/src/App.jsx`: Declares client-side routes with `react-router-dom`:
  - `/` → `Home`
  - `/form` → `FormPage` (renders `Form` component)
  - `/profile` → `Profile`

## Pages and Components
- `Home.jsx`
  - Simple navigation links to `/form` and `/profile`.

- `FormPage.jsx`
  - Thin wrapper that renders `<Form />`.

- `Form.jsx`
  - Handles a unified account form for both login and signup.
  - Local state stores `authMode`, `email`, `password`, and for signup also `first_name` and `last_name`.
  - On submit, sends a POST to `/api/auth` with JSON body:
    - `{ mode: 'login'|'signup', email, password, first_name?, last_name? }`
  - Parses response JSON and displays a small debug preview.
  - On successful login, it saves a subset of the profile in `localStorage` under `auth_profile` and navigates to `/profile`.

- `Profile.jsx`
  - Reads `auth_profile` from `localStorage` and displays a friendly greeting using the stored names.

## Network Calls
- Uses the browser `fetch` API directly:
  - URL: `/api/auth`
  - Method: `POST`
  - Headers: `Content-Type: application/json`
  - Body: `JSON.stringify({...})`
- Expects JSON responses from the FastAPI backend.

## Build and Serve
- Development:
  - Run Vite dev server normally in the `frontend/` directory.
- Production on Vercel:
  - `vercel.json` runs `npm install --prefix frontend` and `npm run build --prefix frontend`.
  - Build output is placed in `frontend/dist` and served statically.
  - All non-`/api` routes rewrite to `index.html` so client-side routing works on refresh.

## Tips for Extending
- Add new pages under `frontend/src/pages/` and route them from `App.jsx`.
- Centralize API calls (optional) in a small client module if the app grows.
- Consider handling and surfacing backend errors more granularly in the UI as needs evolve.

