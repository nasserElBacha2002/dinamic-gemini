# 09 — OpenAPI crosscheck

| Source | Operations |
|--------|----------:|
| FastAPI registry (APIRoute + docs Starlette) | 222 |
| `app.openapi()` / `openapi-discovered.yaml` path methods | **214** (business APIRoute; docs UI omitted from schema paths) |
| Inventory JSON/CSV | 222 |
| Delta inventory − OpenAPI | **8** (`GET`/`HEAD` × `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`) |

## Discrepancies

- Built-in `/docs`, `/redoc`, `/openapi.json` are **Starlette `Route`**, not `APIRoute`; included manually in inventory (VERIFIED).
- OpenAPI schema focuses on API operations; documentation UI routes may not appear as `paths` entries.
- Inventory annotated export: `openapi-discovered.yaml` with `x-audit-evidence`, `x-dast-priority`, `x-source-file`, `x-bola-status`.

## Documented vs registered

- No separate committed OpenAPI file is the source of truth; schema is generated from code.
- Classification: **DOCUMENTED_AND_REGISTERED** for operations present in `app.openapi()`; docs UI = **REGISTERED_NOT_DOCUMENTED** as API ops (they're UI).
