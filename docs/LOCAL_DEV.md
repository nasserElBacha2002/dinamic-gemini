# Local development launcher

Un solo comando desde la raíz del repo levanta backend y frontend.

## Opción recomendada: script `.sh`

Desde la **raíz del repo**:

```bash
./dev.sh
```

- Backend con el Python de **`.venv`** (puerto 8000; `PORT=8001 ./dev.sh` si 8000 está ocupado).
- Frontend con `npm run dev` en `frontend/`.
- Ctrl+C cierra ambos.

No hace falta Node en la raíz ni `npm install` para esto.

---

## Alternativa: `npm run dev`

Si prefieres usar npm desde la raíz:

```bash
npm install   # una vez
npm run dev
```

Mismo resultado: backend (via `scripts/run-backend.js`) + frontend con concurrently.

## Prerequisites

- **Backend:** Python 3.9+ with a virtual environment at repo root:
  ```bash
  python -m venv .venv
  source .venv/bin/activate   # Windows: .venv\Scripts\activate
  pip install -e .
  ```
- **Frontend:** Node 18+ and npm. From repo root:
  ```bash
  cd frontend && npm install && cd ..
  ```
- **Root:** Install the dev launcher dependency (once) — solo si usas `npm run dev`:
  ```bash
  npm install
  ```

## Si el backend no arranca (puerto 8000 en uso)

### Backend doesn’t start: “Address already in use”

If you see `[Errno 48] Address already in use`, port **8000** is taken (e.g. a previous run or another app). Either:

- Free the port, e.g. find and kill the process:
  ```bash
  lsof -i :8000
  kill <PID>
  ```
- Or use another port and point the frontend proxy to it:
  ```bash
  PORT=8001 ./dev.sh
  # o con npm: PORT=8001 npm run dev
  ```
  Then set the frontend API base URL to `http://localhost:8001` (e.g. in `frontend/.env` or Vite proxy) so the UI talks to the backend.

## Assumptions

- Virtual environment lives at **`.venv`** in the repo root. The launcher uses this so you don’t have to activate the venv before running `npm run dev`.
- Backend is started from the repo root so the `src` package resolves correctly.
- Frontend runs from `frontend/`; the Vite proxy and env are unchanged.

## Run backend or frontend only

- Backend only: `npm run dev:backend`
- Frontend only: `npm run dev:frontend`
