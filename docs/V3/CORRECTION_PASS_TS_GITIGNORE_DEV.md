# Correction pass — TypeScript migration, .gitignore, dev command

## 1. Files to create

- `frontend/tsconfig.json` — TypeScript config (strict, JSX react-jsx, include src).
- `frontend/tsconfig.node.json` — Config for Vite config (if we use .ts later); optional, can be skipped if Vite stays .js.
- `frontend/src/api/types.ts` — DTOs: Inventory, Aisle, CreateInventoryRequest, CreateAisleRequest, ApiError (for client throws).
- Root `package.json` — Scripts dev, dev:backend, dev:frontend; devDependency concurrently.
- New frontend source files as .tsx/.ts (see migration): main.tsx, App.tsx, theme.ts, api/client.ts, pages/*.tsx, components/*.tsx.

## 2. Files to modify

- `frontend/package.json` — Add TypeScript, @types/react, @types/react-dom; keep existing scripts (Vite handles TS).
- `frontend/index.html` — Script src from main.jsx to main.tsx.
- `.gitignore` — Add node_modules/; under *.json exclusions add !tsconfig.json and !tsconfig.node.json; ensure frontend build output remains ignored (dist/ already present).
- Delete old .jsx/.js source files after creating .tsx/.ts equivalents.

## 3. Migration approach (JS → TS)

- Add strict tsconfig: "strict": true, "noImplicitAny": true (or rely on strict), "jsx": "react-jsx", "module": "ESNext", "target": "ES2020".
- Define types in api/types.ts aligned with backend schemas: Inventory (id, name, status, created_at?), Aisle (id, inventory_id, code, status, created_at, updated_at, error_code?, error_message?), request bodies, and ApiError (status, data) for thrown fetch errors.
- API client: type return values as Promise<Inventory[]>, Promise<Inventory>, etc.; type request bodies; extend Error in catch with status/data or use a custom ApiError interface and type guard.
- Components: type props as interfaces (CreateInventoryDialogProps, etc.); type useState with generics (useState<Inventory | null>(null), etc.); type useParams() for inventoryId (string | undefined).
- No `any`; use `unknown` in handleResponse if needed and narrow after.
- Rename files in place: create new .tsx/.ts with same content (typed), then remove .jsx/.js.

## 4. .gitignore changes

- Add `node_modules/` (root and any subdirectory).
- In the "*.json" exclusion block, add `!tsconfig.json` and `!tsconfig.node.json` so TypeScript config files are not ignored.
- Keep existing dist/, .env, etc. No change to backend ignores beyond ensuring node_modules is present.

## 5. Run frontend + backend together

- Use root `package.json` with `concurrently`: one command runs both uvicorn (backend) and `cd frontend && npm run dev` (frontend).
- Scripts: "dev": "concurrently -n be,fe \"npm run dev:backend\" \"npm run dev:frontend\"", "dev:backend": "python -m uvicorn src.api.server:app --reload", "dev:frontend": "cd frontend && npm run dev".
- Backend must run from repo root so Python module path is correct. Document in root README or frontend README: "From repo root: npm run dev (requires: pip install -e . or venv with uvicorn, and cd frontend && npm install)."

**Command to run both:** From repository root, run `npm run dev`. Ensure Python venv is activated and `cd frontend && npm install` has been run once.
