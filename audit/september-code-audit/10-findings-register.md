# 10 — Findings register

Estado: OPEN (ninguno remediado en fase 1).  
Confianza: VERIFIED salvo nota.

| ID | Título | Categoría | Severidad | Confianza | Componente | Ubicación | Evidencia | Impacto | Recomendación | Validación |
|----|--------|-----------|-----------|-----------|------------|-----------|-----------|---------|---------------|------------|
| SEC-001 | List/get inventarios sin filtro tenant | Seguridad / AuthZ | HIGH | VERIFIED | Backend | `list_inventory_list_items.py:169`, `inventories.py:190-423` | `list_all`/`get_by_id` sin `InventoryAccessPolicy` | IDOR cross-client si `company_admin` | Filtrar por `principal.client_id` / policy en todos los reads | Tests company_admin matrix |
| SEC-002 | Clients list/get sin tenant | Seguridad / AuthZ | HIGH | VERIFIED | Backend | `clients` routes + list/get UCs | JWT only | Enumeración/lectura cross-tenant | Scope platform vs company | Tests IDOR |
| SEC-003 | Refresh tokens solo in-memory | Seguridad / AuthN | HIGH | VERIFIED | Backend | `auth/service.py:69-70` | Dict proceso | Logout/refresh roto multi-instancia | Store durable o sticky+documentar | Restart/multi-worker test |
| SEC-004 | JWT en localStorage FE | Seguridad | MEDIUM | VERIFIED | Frontend | `features/auth/storage.ts:10-44` | access+refresh JSON | XSS→session theft | httpOnly cookie o mitigar XSS strict | Security review FE |
| SEC-005 | OpenAPI/docs expuestos por defecto | Seguridad | MEDIUM | VERIFIED | Backend | `server.py` FastAPI defaults; `api_key_policy` bypass | `/docs` `/openapi.json` | Superficie info | Desactivar en prod / proteger | Curl prod-like |
| SEC-006 | Mobile npm critical/high | Dependencias | HIGH | VERIFIED advisory; INFERRED reachability | Mobile | `npm audit` — `tar` critical + 13 high | audit JSON | Supply-chain / toolchain | Override/upgrade; evaluar runtime | Advisory + SBOM |
| SEC-007 | FE npm moderate (vitest mocker) | Dependencias | LOW | VERIFIED | Frontend | vitest/@vitest/mocker | DevDep | Limitado a toolchains test | Upgrade cuando viable | npm audit |
| ARCH-001 | Domain→pipeline import | Arquitectura | MEDIUM | VERIFIED | Backend | `domain/traceability_artifact/builder.py` | Boundary R1 FAIL | Acoplamiento | Mover adapter | Re-run architecture audit |
| ARCH-002 | Application→api schemas | Arquitectura | MEDIUM | VERIFIED | Backend | `llm_cost_snapshot_public.py` | Boundary R2 FAIL | Inversión capas | DTO en application/domain | Audit |
| ARCH-003 | Rutas API excesivas (`aisles.py`) | Arquitectura | MEDIUM | VERIFIED heurística | Backend | `aisles.py` ~2151 LOC | R3 signals | Mantenibilidad | Split routers | Review |
| ARCH-004 | Complejidad FE archivos >1000 | Arquitectura | LOW | VERIFIED tool | Frontend | complexity report | 8 files | Deuda | Modularizar | — |
| FUNC-001 | Sin close/reopen inventario | Funcional | MEDIUM | VERIFIED | Backend | inventories routes | Ausencia | Operadores sin lifecycle explícito | Diseñar API o documentar | Product |
| FUNC-002 | Offline aisle solo vía ZIP | Funcional | MEDIUM | VERIFIED | Mobile | offline ops types | No CREATE_AISLE | Fricción sync | Op sync o docs | E2E |
| FUNC-003 | Review queue FE dead | Funcional | LOW | VERIFIED | Frontend | ReviewQueueRedirect | Redirect home | Confusión | Remover o restaurar | — |
| FUNC-004 | Dual queues flags mobile | Funcional | MEDIUM | VERIFIED | Mobile | featureFlagCompatibility | Warnings | Sync inconsistente | Mutex flags | Tests |
| FUNC-005 | Legacy LLM/OCR en árbol | Funcional | INFO | VERIFIED | Backend | legacy_processing_guard | Blocked new starts | Ruido | — | — |
| TEST-001 | Gate progressive permite mobile high vulns | Testing/Ops | MEDIUM | VERIFIED | Tooling | gate_policy | Findings allowed | Falsa sensación de seguridad | Política más estricta mobile | Gate |
| TEST-002 | Falta matrix IDOR tenant | Testing | HIGH | VERIFIED gap | Tests | — | Cobertura incompleta | Regresión AuthZ | Añadir tests (fase post) | — |
| TEST-003 | security-exceptions.json missing | Ops | HIGH | VERIFIED | Audit gate | `audit/security-exceptions.json` | Gate FAIL | Bloquea deploy gate local | Crear archivo vacío/política | Gate |
| OPS-001 | Gitleaks Docker BLOCKED aquí | Ops | MEDIUM | VERIFIED | Audit | run_security_audit.sh | exit 126 | Secret scan oficial falla | Asegurar Docker CI | CI |
| OPS-002 | Host gitleaks 0 leaks | Ops | INFO | VERIFIED | — | gitleaks-host-report | Alternativo PASS | — | Mantener en CI también | — |
| OPS-003 | `.gitleaksignore` fingerprint inválido | Ops | LOW | VERIFIED | `.gitleaksignore` | Warning host scan | Ruido | Corregir entry | — |
| DATA-001 | Zip-bomb / zip-slip residual | Seguridad | UNKNOWN | UNKNOWN | Imports ZIP | packages | Sin prueba dinámica | DoS potencial | Fuzz fase 2 | — |
| INFO-001 | Bandit 0 high / 102 medium | Seguridad | INFO | VERIFIED | Bandit | raw JSON | Señales | Triage selectivo | — | — |
| INFO-002 | pip-audit clean | Dependencias | INFO | VERIFIED | Backend | pip-audit | 0 | — | — | — |
| INFO-003 | TXT filename traversal mitigated | Seguridad | INFO | VERIFIED | TXT parser | lines 375-376 | Control positivo | Mantener tests | — | — |
| INFO-004 | CORS hosted fail-safe | Seguridad | INFO | VERIFIED | security_headers | normalize | Control positivo | — | — | — |
| INFO-005 | Upload scope en assets | Seguridad | INFO | VERIFIED | assets routes | Depends scope | Control positivo | Extender a list/get | — | — |
| INFO-006 | No AGENTS.md / pre-commit | Ops | INFO | VERIFIED | repo root | Ausencia | Onboarding | Opcional | — | — |

## Conteos

- CRITICAL: 0  
- HIGH: 5 (SEC-001,002,003,006 + TEST-002/TEST-003 contados en tabla; unificar: **SEC×4 HIGH + TEST-002 + TEST-003** → reportar **6 HIGH** si se incluyen tooling gaps como HIGH)

Ajuste ejecutivo: HIGH de seguridad producto = SEC-001,002,003,006 (4) + AuthZ test gap TEST-002 (1) + gate exceptions TEST-003 (1 ops) = **6 HIGH** en registro amplio; ver executive summary (5 HIGH seguridad+deps priorizados + 1 tooling).
