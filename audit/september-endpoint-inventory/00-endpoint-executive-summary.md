# 00 — Endpoint inventory executive summary

| Field | Value |
|-------|-------|
| Commit | `7e254f35c68610931f0f2aff5bc936a52bc77b39` |
| Branch | `DIN-357` |
| Started UTC | `2026-09-14T16:02:58Z` |
| Source of truth | FastAPI `app.routes` introspection + router source |
| Verdict | **READY_FOR_SECURITY_REPOSITORY** |

## Totals

| Metric | Count |
|--------|------:|
| Total method+path | **222** |
| APIRoute-derived | 214 |
| Built-in docs (Starlette Route) | 8 |
| Public (auth_required=false) | 12 |
| Authenticated | 210 |
| POTENTIAL_BOLA | 154 |
| CONTROL_VERIFIED (tenant scope dep) | 33 |
| AUTHORIZATION_UNKNOWN | 20 |
| NOT_APPLICABLE | 15 |

## By method

| Method | Count |
|--------|------:|
| DELETE | 2 |
| GET | 118 |
| HEAD | 4 |
| PATCH | 6 |
| POST | 87 |
| PUT | 5 |

## By module

| Module | Count |
|--------|------:|
| admin | 4 |
| aisle_locations | 4 |
| aisle_revisions | 5 |
| aisles | 30 |
| analytics | 8 |
| assets | 16 |
| auth | 4 |
| authoritative_local | 2 |
| capture | 7 |
| clients | 39 |
| code_scans | 5 |
| config | 3 |
| dinamic_scanner_txt | 2 |
| docs | 8 |
| inventories | 40 |
| inventory_exports | 3 |
| jobs_processing | 21 |
| local_csv_imports | 3 |
| local_inventory_packages | 3 |
| observability | 1 |
| ops | 3 |
| positions | 7 |
| preliminary | 2 |
| review_queue | 1 |
| server_reprocess | 1 |

## DAST priority

| Priority | Count |
|----------|------:|
| CRITICAL | 15 |
| HIGH | 161 |
| INFORMATIONAL | 6 |
| LOW | 23 |
| MEDIUM | 17 |

## Principales riesgos

1. **AuthZ tenant incompleta** en list/get inventarios/clients y muchos nested `{inventory_id}` sin `require_inventory_client_scope` (POTENTIAL_BOLA; CRITICAL subset documentado).
2. **Docs/OpenAPI públicos** (`/docs`, `/openapi.json`, `/redoc`) sin JWT.
3. **Uploads/imports** (assets, packages, TXT, CSV) — HIGH DAST.
4. **Jobs/process** — costo IA / CPU — HIGH.
5. **Login** — CRITICAL brute-force / credential stuffing surface.

## Incertidumbres

- Autorización efectiva dentro de use cases (más allá de Depends) no se ejecutó dinámicamente.
- Matching FE/mobile es heurístico por literales de path (falsos negativos/positivos).
- No se enviaron requests; códigos HTTP observables = inferidos de handlers/schemas.
- Workers no exponen HTTP propio (VERIFIED: cola SQL / embedded thread).
