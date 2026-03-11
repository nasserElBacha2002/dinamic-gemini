# Dinamic Inventory v3 — Frontend

React + Material UI frontend (TypeScript) for the v3 inventories and aisles API.

## Setup

```bash
npm install
```

From the **repository root**, to run both frontend and backend with one command:

```bash
npm install          # install root devDependency (concurrently)
cd frontend && npm install
npm run dev          # starts backend (uvicorn) + frontend (Vite)
```

Backend runs on port 8000; frontend on port 5173 and proxies `/api` and `/health` to the backend.

## Development (frontend only)

Start the Vite dev server (port 5173). It proxies `/api` and `/health` to the backend (default `http://localhost:8000`).

```bash
npm run dev
```

Start the backend from the repo root first:

```bash
python -m uvicorn src.api.server:app --reload
```

## TypeScript

- Source is TypeScript (`.ts`/`.tsx`). API types and DTOs live in `src/api/types.ts`.
- Type-check without building: `npm run typecheck`

## Build

```bash
npm run build
```

Output is in `dist/`.

## Environment

- `VITE_API_BASE_URL` — Optional. Leave empty to use the dev proxy. Set to the full API base URL (e.g. `http://localhost:8000`) when serving the built app from another origin.
