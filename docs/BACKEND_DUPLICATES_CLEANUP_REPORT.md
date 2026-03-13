# Backend duplicates cleanup report (post-migration)

## 1. Summary

After the repository reorganization that moved backend code under `backend/`, an audit was performed to find **duplicate backend artifacts** left outside `backend/`. The goal was to remove only clearly redundant copies so the repo has a single backend source of truth under `backend/`, without touching shared root-level files or frontend.

**Findings:**

- No duplicate `src/`, `tests/`, `configs/`, or `pyproject.toml` remained at root (they had been moved into `backend/` during the migration).
- One **stale backend artifact** at root was identified and removed: **`dinamic_gemini.egg-info/`** (Python package metadata from the pre-migration layout).
- Root **`scripts/`** contains only `run-backend.js` (orchestration for `npm run dev:backend`); it is not a duplicate of `backend/scripts/` (which holds `create_aruco.py`). Kept.
- One **stale reference** was updated: **`activate.sh`** now uses `.venv` and `pip install -e backend/` instead of `venv` and `pip install -e .`.

---

## 2. Deleted artifacts

| Artifact | Reason it was safe to remove |
|----------|------------------------------|
| **`dinamic_gemini.egg-info/`** (at repo root) | Stale setuptools metadata from when the package lived at root. The canonical package is now installed from `backend/` via `pip install -e backend/`, which creates `backend/dinamic_gemini.egg-info/`. No script or config references the root egg-info path. `.gitignore` already has `*.egg-info/`, so this was a leftover on-disk artifact. |

---

## 3. Retained artifacts (reviewed, intentionally kept)

| Artifact | Rationale |
|----------|-----------|
| **Root `scripts/`** | Contains only `run-backend.js` (starts backend for `npm run dev:backend`). Not a duplicate of `backend/scripts/` (which has `create_aruco.py`). Root scripts are orchestration; kept. |
| **Root `README.md`** | Project-wide readme; not a backend duplicate. |
| **Root `package.json` / `package-lock.json` / `node_modules/`** | Root dev orchestration (e.g. `npm run dev`); shared, not backend-only. |
| **Root `dev.sh`** | Runs backend + frontend; references `backend/` and `uvicorn src.api.server:app`. Shared. |
| **Root `pytest.ini`** | Points to `backend/tests` and `pythonpath = backend`; root-level test runner config, not a duplicate of backend source. |
| **Root `.env`, `.env.example`** | Environment config; backend loads from cwd (root) when run from root. Shared. |
| **Root `docs/`** | Project documentation. Kept. |
| **Root `output/`** | Runtime output dir; backend uses it via `OUTPUT_DIR`. Shared. |
| **Root `.pytest_cache/`, `.coverage`, `htmlcov/`** | Generated test/coverage artifacts; not copies of backend source. Already in `.gitignore`. Kept. |
| **Root `venv/`** | Legacy virtualenv (old name). `activate.sh` was updated to use `.venv` and `backend/`; `venv/` was not deleted to avoid breaking anyone still using it manually. Can be removed in a later cleanup if unused. |
| **Root `backend/`** | Single backend source of truth; not touched. |
| **Root `frontend/`** | Frontend app; not touched. |

---

## 4. Updated references

| File | Change |
|------|--------|
| **`activate.sh`** | Switched from `venv` to `.venv` and from `pip install -e ".[dev]"` to `pip install -e backend/` and `pip install -e "backend/[dev]"` so activation and install instructions match the current layout and dev.sh/README. |

No other references pointed at the removed root `dinamic_gemini.egg-info/`; no further updates were required.

---

## 5. Risks and deferred items

- **Root `venv/`**  
  Legacy virtualenv; `activate.sh` no longer uses it. Retained to avoid breaking manual use. If the team confirms it is unused, it can be removed in a follow-up (and optionally added to `.gitignore` if not already covered).

- **Generated/cache dirs at root**  
  `.pytest_cache/`, `.coverage`, `htmlcov/` are generated when running pytest from root. They are not “duplicate backend source” and were left in place; `.gitignore` already excludes them.

- **Double egg-info**  
  If someone runs `pip install -e .` from root by mistake (e.g. old habit), a new root `dinamic_gemini.egg-info` could be created again (root has no `pyproject.toml` now, so that would fail). No change made; documenting here for awareness.

---

## 6. Validation notes

- **Backend load:** After removing root `dinamic_gemini.egg-info/`, `from src.api.server import app` and `app.title` were checked from repo root with the venv that has `pip install -e backend/`. Backend loads correctly.
- **Tests:** `pytest backend/tests/test_config.py` (excluding the known failing `test_output_dir_normalization`) was run from root; 21 tests passed.
- **Paths:** No script or config was found that references the root `dinamic_gemini.egg-info` path; removal does not break any referenced path.

---

## Conclusion

One duplicate backend artifact at root (**`dinamic_gemini.egg-info/`**) was removed, and one script (**`activate.sh`**) was updated to match the current backend layout. All other reviewed root items are either shared or orchestration and were kept. The repository has a single clear backend source of truth under `backend/`, and validation confirms backend and tests still work after cleanup.
