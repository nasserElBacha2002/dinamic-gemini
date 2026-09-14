# 09 — Cross-layer consistency

## Frontend vs backend

| Tema | Estado | Evidencia |
|------|--------|-----------|
| Auth gate UI | Solo UX | `App.tsx` vs JWT backend |
| Admin AI page | UI username + backend `id==admin` | Alineado parcialmente |
| Review queue | FE redirect; API viva | Inconsistencia producto |
| Tipos inventarios | Paginated contract documentado en route | FE debe consumir objeto no array |

## Mobile vs backend

| Tema | Estado |
|------|--------|
| Tokens | SecureStore vs FE localStorage — asimetría |
| Offline validation | `offlineSupplierLabelValidator` ↔ `LabelValidationService` — parity intent; no re-prueba exhaustiva esta fase |
| Aisle create offline | No espejo API CREATE; ZIP import |
| DTO flags | Feature flags dual-queue — riesgo inconsistencia |

## ORM/migraciones

SQL Server schema + migraciones versionadas bajo `backend` (hasta series 009x según PROJECT_CONTEXT). Validación runtime via schema guard `/ready`. No se reaplicaron migraciones.

## `.env.example` vs consumo

Plantilla raíz extensa; settings en `env_settings/grouped_settings.py`. Riesgo UNKNOWN de keys huérfanas sin diff automatizado en esta fase.

## Docker / Compose vs requisitos

`backend/docker-compose.yml` API + secrets mount; worker Dockerfile separado. Dev OpenCloud docs en `docs/deployment/`.

## CI vs local

| Local full audit | CI main gate |
|------------------|--------------|
| Incluye architecture + gitleaks Docker | Backend/FE/security audits más estrechos |
| Mobile npm audit en collectors | Mobile workflow separado |
| Gate exige security-exceptions.json | CI workflows no necesariamente igual |

## Docs vs código

`PROJECT_CONTEXT.md` (2026-08-27) aún describe IDOR gaps — **consistente** con hallazgos actuales. README subdocumenta mobile/audit suite.

## Límites de tamaño upload

Documentados en deployment upload-proxy docs + settings + mobile/FE consumers — verificar Nginx/proxy en deploy (UNKNOWN sin inspeccionar prod config values).
