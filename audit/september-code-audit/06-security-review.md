# 06 — Security review (manual)

Clasificación de evidencia: VERIFIED / INFERRED / UNKNOWN.  
Sin DAST. Sin exfiltración de secretos (`.env` gitignored; no se listan valores).

## 9.1 Autenticación

| Tema | Hallazgo | Evidencia | Severidad |
|------|----------|-----------|-----------|
| JWT HS256 | Emisión/validación Bearer | `auth/security.py`, `auth/dependencies.py` | INFO |
| Usuarios solo env | Admin + opcional Jairo; sin DB users | `auth/service.py` | INFO (producto) |
| Refresh in-memory | `_REFRESH_TOKENS` dict de proceso | `auth/service.py:69-70` | **HIGH** (ops/authz continuity) |
| Cookies sesión | No usadas para auth | VERIFIED absent | INFO |
| API key opcional | Solo si `API_KEY` + prefixes | `server.py`, `api_key_policy.py` | INFO |

## 9.2 Autorización / multi-tenancy

| Tema | Hallazgo | Evidencia | Severidad |
|------|----------|-----------|-----------|
| Policy inventario | `InventoryAccessPolicy` fail-closed 404 | `inventory_access_policy.py` | INFO (control bueno) |
| Uploads scoped | `require_inventory_client_scope` en assets | `assets.py` | INFO |
| List inventarios | `list_all()` sin filtro por principal | `list_inventory_list_items.py:169`; route `inventories.py:190-218` | **HIGH** (IDOR si `company_admin`) |
| Get inventario | `GetInventory` solo `get_by_id` | `inventories.py:409-423` | **HIGH** (mismo patrón) |
| Clients list/get | JWT only; list_all / get_by_id | `clients.py` + use cases | **HIGH** |
| Contraste | Algunos exports/uploads sí usan scope | inventories ~324 | INFO |

**Confianza:** VERIFIED código. **Explotabilidad:** INFERRED — requiere principals con `client_id` (`AUTH_*_CLIENT_ID`). Con solo `platform_admin` unbound, acceso global es diseño actual.

## 9.3 Entradas / archivos

| Tema | Estado | Evidencia |
|------|--------|-----------|
| TXT path traversal filename | Mitigado (`..` `/` `\`) | `dinamic_scanner_txt_parser.py:375-376` |
| Upload size limits | Config + endpoint | `config.py` upload-limits |
| ZIP packages | Import path presente | `local_inventory_packages.py` — zip-bomb depth UNKNOWN sin prueba dinámica |
| SQL injection | Repos tipados / ODBC params — residual UNKNOWN sin SAST deep | Bandit no reportó HIGH SQLi |

## 9.4 IA / imágenes

| Tema | Estado |
|------|--------|
| Prompt injection vía labels | Riesgo **MEDIUM** inherente; prompts supplier + imagen — necesita fase SAST/DAST especializada |
| Circuit breaker / concurrency fallback | Presente en settings/start_aisle_processing (VERIFIED existencia; no re-probado exhaustivo) |
| Logs de prompts | Flags debug (`DEBUG_LOG_FULL_ANALYSIS_PROMPT`) — riesgo si enabled en prod |

## 9.5 Infra / config

| Tema | Hallazgo | Severidad |
|------|----------|-----------|
| Swagger/OpenAPI default | `FastAPI()` sin desactivar docs; bypass API-key list | **MEDIUM** |
| CORS | Normalización fail-safe hosted | INFO positivo (`security_headers.py`) |
| `.env` local | Existe, gitignored | INFO — no auditar valores |
| Gitleaks host | 0 leaks | PASS alternativo |
| Gitleaks Docker oficial | BLOCKED | OPS |

## 9.6 Dependencias

| Target | Resultado | Severidad registro |
|--------|-----------|--------------------|
| pip-audit | 0 | INFO |
| FE npm high | 0 high (2 moderate vitest) | LOW |
| Mobile npm | 1 critical (`tar`), 13 high (expo/metro/js-yaml/…) | **HIGH** (supply-chain / toolchain); reachability runtime app **INFERRED** limitada |

## Frontend tokens

`localStorage` `dinamic_auth_session` guarda access+refresh (`frontend/src/features/auth/storage.ts`) — **MEDIUM/HIGH** XSS → token theft. Mobile usa SecureStore (mejor).

## Controles solo-frontend

`RequireUsernameAdmin` / route gate en `App.tsx` — **no son seguridad**; backend debe enforce (AI config sí filtra `id==admin`).
