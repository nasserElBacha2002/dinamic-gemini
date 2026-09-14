# 12 — Phase 2 handoff

## Módulos HTTP detectados (para inventario formal posterior)

Montados desde `backend/src/api/server.py` (VERIFIED):

- `/auth` — login, refresh, logout
- `/api/v3/...` — inventories, aisles, assets, positions, clients, capture_sessions, jobs/process, local_csv_imports, local_inventory_packages, dinamic_scanner_txt_imports, analytics, reviews/review_queue, config, admin AI, processing observability, server_reprocess, aisle_locations, client_position_labels, etc.
- `/health`, `/ready`, `/metrics`
- OpenAPI: `/docs`, `/redoc`, `/openapi.json` (default)

**No se enumera aquí la lista completa de paths** (fase 2).

## Autenticación

- Bearer JWT HS256 (`AUTH_TOKEN_SECRET`)
- Refresh opaco in-memory
- Optional `X-API-Key` path-scoped
- Principals env: primary admin + optional Jairo

## Roles

- `platform_admin` (unbound)
- `company_admin` (requires `client_id`)
- Legacy claim `administrator` aceptado como platform
- AI config inspection: solo `AuthUser.id == "admin"`

## Tenants / recursos

- Tenant key: `client_id`
- Recursos: inventory, aisle, asset, job, position, product_record, capture_session, client, supplier, extraction_profile, import/export packages, labels

## Uploads / imports

- Multipart images/video (assets, capture)
- Supplier reference images
- Local CSV, ZIP inventory package, Dinamic TXT

## Integraciones

- LLM: Gemini, OpenAI, Anthropic (DeepSeek legacy read)
- Storage: local, S3, GCS
- SQL Server ODBC

## Operaciones críticas

- Start/cancel/retry aisle processing
- Authoritative local result sync / finalization
- Soft-delete inventories
- Position merge
- Label profile activation
- Package/TXT confirm imports

## Datos / usuarios de prueba sugeridos (fase 2)

- Disposable SQL DB
- Dos clients (A/B) + company_admin tokens scoped
- platform_admin token
- Synthetic inventory/aisle/asset IDs (ver comentarios `security-audit.yaml` / docs DAST seed)
- **No** credenciales reales ni producción

## Incertidumbres pendientes

| Tema | Estado |
|------|--------|
| Gitleaks Docker en este host agente | BLOCKED; host scan OK |
| Reachability real de vulns mobile `tar`/metro | INFERRED |
| Zip-bomb resistance | UNKNOWN |
| Proxy Nginx body limits en OpenCloud | UNKNOWN sin config deploy viva |
| security-agents instalado | NOT_CONFIGURED |

## Entregables esperados fase 2

1. Inventario completo endpoints + métodos + authz expected  
2. Plan SAST (semgrep/bandit triage)  
3. Plan DAST non-mutating contra localhost disposable  
4. Casos IDOR explícitos company_admin  
