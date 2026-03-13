# Repository structure

This repo separates **backend** (Python API and pipeline) and **frontend** (React/TypeScript) so the layout is clear and maintainable.

## Top-level layout

| Path | Purpose |
|------|--------|
| **`backend/`** | Python backend: API, domain, application layer, pipeline, jobs, persistence. Install with `pip install -e backend/` from repo root. |
| **`frontend/`** | React/TypeScript app. Run with `cd frontend && npm run dev`. |
| **`docs/`** | Project and stage documentation. |
| **`output/`** | Runtime output directory (backend writes here; configurable via `OUTPUT_DIR`). |
| **`scripts/`** | Root orchestration (e.g. `run-backend.js` for `npm run dev:backend`). |

## Where to add code

- **Backend (API, use cases, pipeline, jobs, DB)** → `backend/src/`. Keep existing package name `src` and import style `from src.*`.
- **Backend tests** → `backend/tests/`.
- **Frontend (pages, components, API client, hooks)** → `frontend/src/`.
- **Frontend tests** → `frontend/tests/` (or under `frontend/src/` as per project convention).
- **Project-wide docs** → `docs/`.

## Running the app

- **Backend + frontend together:** from repo root run `./dev.sh` (starts API and Vite dev server).
- **Backend only:** from repo root, `uvicorn src.api.server:app --reload` (after `pip install -e backend/`).
- **Frontend only:** `cd frontend && npm run dev`.

## Backend install and tests

From repo root:

```bash
pip install -e backend/
pytest
```

Backend runs with process cwd at repo root so `.env` and `output/` paths behave as before.
