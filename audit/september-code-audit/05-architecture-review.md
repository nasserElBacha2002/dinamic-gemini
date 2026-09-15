# 05 — Architecture review

## Vista de alto nivel (VERIFIED)

```
Frontend (Vercel) ──JWT──▶ FastAPI (/api/v3, /auth) ──ODBC──▶ SQL Server
Mobile (Expo)     ──JWT──▶        │
                                  ├── workers (embedded / on-demand / dedicated)
                                  ├── artifacts local|S3|GCS
                                  └── LLM providers (Gemini/OpenAI/Anthropic)
```

Entry: `backend/src/api/server.py` (`app = FastAPI(...)`). Worker: `src.jobs.run_worker` / embedded thread.

## Capas backend

| Capa | Path |
|------|------|
| API | `backend/src/api/` |
| Application | `backend/src/application/` |
| Domain | `backend/src/domain/` |
| Infrastructure | `backend/src/infrastructure/` |
| Cross-cutting | `auth/`, `jobs/`, `pipeline/`, `llm/`, `runtime/` |

## Límites de imports (herramienta)

De `audit/raw/backend-import-boundaries.txt` (heurística AST):

| Regla | Estado | Ejemplo |
|-------|--------|---------|
| R1 domain↛api/infra/pipeline | **FAIL** | `domain/traceability_artifact/builder.py` → `pipeline.services.provider_execution_request` |
| R2 application↛api | **FAIL** | `application/services/llm_cost_snapshot_public.py` → `api.schemas.benchmark_schemas` |
| R2b application↛fastapi | PASS | |
| R4 infra↛api | PASS | |

Severidad arquitectónica: **HIGH** como deuda estructural (no RCE). Confianza: VERIFIED tool + paths.

## Complejidad / code smells

- Backend radon: grades C–F numerosas; pylint signals (too_many_args/branches) — FINDINGS high métrico.
- Frontend: 8 archivos >1000 líneas; 53 >300 — FINDINGS.
- Rutas pesadas: `aisles.py` ~2151 líneas (heurística R3).

## Responsabilidades / riesgos

| Tema | Evaluación |
|------|------------|
| Clean architecture | Mayormente respetada; 2 violaciones concretas de boundary |
| Dual pipeline legacy+v3 | LEGACY_LLM/OCR aún en árbol; guardas de start |
| Cola jobs | SQL claim (prod); in-memory fallback — split-brain documentado |
| Feature flags | Múltiples flags mobile/backend — riesgo de configuración inconsistente |
| Documentación | `PROJECT_CONTEXT.md` (2026-08-27) aún útil; README subdocumenta mobile/audit |

## Dependencias entre clientes

- Frontend y mobile son clientes HTTP del mismo API; contratos en `frontend/src/api/types*` y DTOs mobile + `contracts/`.
- Validación de seguridad debe vivir en backend; FE/mobile son UX (VERIFIED patrón auth).
