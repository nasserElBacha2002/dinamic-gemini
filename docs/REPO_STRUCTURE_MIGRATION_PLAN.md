# Repository structure migration plan — backend / frontend separation

## Phase 1 — Audit (current state)

### Top-level classification

| Path | Classification | Notes |
|-----|----------------|--------|
| `src/` | **Backend** | Python application (api, app, config, domain, pipeline, jobs, database, etc.) |
| `tests/` | **Backend** | Python tests; all imports use `src.*` |
| `frontend/` | **Frontend** | React/TypeScript app (already isolated) |
| `configs/` | **Backend** | Empty; reserved for backend config files |
| `scripts/` | **Backend** | Moved to `backend/scripts/` (create_aruco.py). Root `scripts/` holds `run-backend.js` for npm. |
| `docs/` | **Shared** | Project documentation; stays at root |
| `output/` | **Shared/runtime** | Backend write dir (config `OUTPUT_DIR`); keep at root or document |
| `pyproject.toml` | **Backend** | Python package definition, pytest/black/ruff; entry point `src.app:main` |
| `package.json` | **Shared** | Root dev script (concurrently backend + frontend); `dev:backend` uses `scripts/run-backend.js`. |
| `package-lock.json`, `node_modules/` | **Shared** | Root npm deps for dev script |
| `dev.sh` | **Shared** | Runs backend (uvicorn) + frontend (npm run dev); backend started from root |
| `activate.sh` | **Shared** | Venv activation; root |
| `.env`, `.env.example` | **Shared** | Loaded by backend from cwd (root when run from root) |
| `README.md` | **Shared** | Project readme; root |
| `.gitignore`, `.gitattributes` | **Shared** | Root |
| `.venv/`, `venv/` | **Shared** | Python venv at root |
| `dinamic_gemini.egg-info/`, `htmlcov/`, `.pytest_cache/`, `.coverage` | **Backend** | Build/coverage artifacts; currently root |

### Backend boundaries

- **Clearly backend:** `src/`, `tests/`, `pyproject.toml`, `configs/`, `scripts/create_aruco.py`
- **Import surface:** All Python code uses `from src.*` / `import src.*`; no path-based references to repo root
- **Config:** `src.config` uses `load_dotenv()` (cwd) and `OUTPUT_DIR` (default `"output"`); when process cwd is repo root, `output/` is root-level
- **Risks:** Moving `src` and `tests` under `backend/` requires (1) package still installable as `src` so imports stay `src.*`, (2) dev and CI run backend from root with backend on PYTHONPATH or installed as `pip install -e backend/`

### Frontend boundaries

- **Clearly frontend:** `frontend/` (src, tests, package.json, vite, tsconfig) — no move needed
- **Contract:** Frontend calls v3 API; no backend path assumptions

### Root files to keep at root

- `README.md`, `.env.example`, `.gitignore`, `.gitattributes`
- `dev.sh`, `activate.sh`
- `package.json`, `package-lock.json` (root dev orchestration)
- `docs/`
- `output/` (runtime; backend config points here)
- `.env` (optional; can stay root so backend loaded from root finds it)

### Root files to remove or relocate

- `pyproject.toml` → move to `backend/`
- `configs/`, `scripts/` → move into `backend/`
- `src/`, `tests/` → move into `backend/`

---

## Phase 2 — Target structure

```text
backend/
  src/                    # Python package (imports remain "src.*")
  tests/
  configs/
  scripts/
  pyproject.toml          # readme = "../README.md"
  README.md               # Short "Backend for Dinamic Inventory"

frontend/                 # Unchanged
  src/
  tests/
  package.json
  ...

# Root
  README.md
  REPO_STRUCTURE.md       # Where to add new code, backend vs frontend
  docs/
  output/
  .env, .env.example
  dev.sh                  # Install backend: pip install -e backend/; uvicorn src.api.server:app
  package.json            # dev:backend can call backend script or keep npm script
  pytest.ini              # testpaths = backend/tests, pythonpath = backend
  activate.sh
  .gitignore, .gitattributes
```

### Design decisions

1. **Package name remains `src`**  
   No change to Python imports; `backend/pyproject.toml` declares the same package and entry point. Install with `pip install -e backend/` from repo root.

2. **Run backend from root**  
   After `pip install -e backend/`, `uvicorn src.api.server:app` and `python -m src.app` work from root; cwd stays root so `output/` and `.env` behave as today.

3. **Pytest from root**  
   Root `pytest.ini` sets `pythonpath = backend` and `testpaths = backend/tests` so `pytest` at root runs backend tests and resolves `src` via `backend/src`.

4. **No frontend move**  
   `frontend/` already separates the React app; only backend is relocated under `backend/`.

5. **Egg-info / coverage**  
   After move, `pip install -e backend/` creates `backend/dinamic_gemini.egg-info` (or similar); coverage remains for package `src`.

---

## Migration steps (execution)

1. Create `backend/`.
2. Move `src/` → `backend/src/`, `tests/` → `backend/tests/`, `configs/` → `backend/configs/`, `scripts/` → `backend/scripts/`.
3. Move `pyproject.toml` → `backend/pyproject.toml`; set `readme = "README.md"` (backend’s own README; setuptools does not allow readme outside the package dir).
4. Add root `pytest.ini`: `testpaths = backend/tests`, `pythonpath = backend`, addopts for coverage.
5. Update `dev.sh`: ensure backend installed from `backend/` (e.g. `pip install -e backend/` once), then `uvicorn src.api.server:app` unchanged.
6. Add `backend/README.md` and root `REPO_STRUCTURE.md`.
7. Update root `README.md`: install instructions use `pip install -e backend/`, and reference `backend/` and `frontend/`.

---

## Execution summary (done)

- Created `backend/` and moved `src/`, `tests/`, `configs/`, `scripts/`, `pyproject.toml` into it.
- Backend `pyproject.toml` uses `readme = "README.md"` (backend’s README).
- Root `pytest.ini` added: `testpaths = backend/tests`, `pythonpath = backend`.
- Root `dev.sh` updated: optional `pip install -e backend/`, then uvicorn as before.
- Root `scripts/run-backend.js` added for `npm run dev:backend` (uses `.venv` and uvicorn).
- Root `REPO_STRUCTURE.md` and `backend/README.md` added; root `README.md` updated for `backend/` and install steps.

---

## Import / path / tooling risks

| Risk | Mitigation |
|------|------------|
| Imports break | Keep package name `src` and install from `backend/`; no import edits |
| Pytest cannot find tests or src | Root pytest.ini with pythonpath=backend, testpaths=backend/tests |
| Coverage wrong | addopts `--cov=src`; coverage runs over loaded package (backend/src) |
| output/ path | Backend runs from root; OUTPUT_DIR default "output" stays root/output |
| .env not found | Backend process cwd = root; load_dotenv() finds root .env |
| package.json dev:backend | Add root `scripts/run-backend.js` so `npm run dev:backend` works (uses .venv and uvicorn). |
