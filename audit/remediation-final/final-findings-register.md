# Final findings register

| Finding ID | Fuente | Categoría | Severidad original | Certeza | Estado anterior | Estado final | Evidencia | Tests | Riesgo residual | Decisión |
|------------|--------|-----------|--------------------|---------|-----------------|--------------|-----------|-------|-----------------|----------|
| SEC-001 | Internal audit | AuthZ inventories | HIGH | VERIFIED | OPEN | VERIFIED_FIXED | InventoryAccessPolicy + scoped list/get/soft-delete | Stage2 UC/HTTP/JWT/SQL | ~140 other endpoints still out of Stage2 scope | Keep Stage3 backlog |
| SEC-002 | Internal audit | AuthZ clients | HIGH | VERIFIED | OPEN | VERIFIED_FIXED | ClientAccessPolicy + platform create | Stage2 suites | Nested routes beyond Stage2 | Stage3 |
| SEC-003 | Internal audit | AuthN refresh | HIGH | VERIFIED | OPEN | DEFERRED | In-memory refresh store unchanged | — | Multi-instance logout/refresh | Product decision |
| SEC-004 | Internal audit | FE JWT storage | MEDIUM | VERIFIED | OPEN | RISK_ACCEPTED | localStorage pattern unchanged | — | XSS session theft | FE hardening backlog |
| SEC-005 | Internal audit | OpenAPI exposure | MEDIUM | VERIFIED | OPEN | DEFERRED | Defaults unchanged | — | Info surface in prod if misconfigured | Ops config |
| SEC-006 | npm audit mobile | Dependencies | HIGH | VERIFIED advisory | OPEN | RISK_ACCEPTED | `security-exceptions.json` | npm audit exit 1 high | Transitive Expo/tar | Upgrade cadence |
| SEC-007 | npm audit FE | Dependencies | LOW | VERIFIED | OPEN | RISK_ACCEPTED | vitest mocker | npm audit moderate | Dev-only | Upgrade vitest |
| ARCH-001 | Architecture audit | Domain→pipeline | MEDIUM | VERIFIED | OPEN | VERIFIED_FIXED | Constant in domain; builder imports domain | `test_layer_import_boundaries` | None for this edge | Closed |
| ARCH-002 | Architecture audit | Application→api | MEDIUM | VERIFIED | OPEN | VERIFIED_FIXED | DTO in application/schemas | architecture + cost snapshot paths | None for this edge | Closed |
| ARCH-003 | Heuristic | aisles.py size | MEDIUM | VERIFIED | OPEN | DEFERRED | No router split | — | Maintainability | Separate refactor |
| ARCH-004 | Tool | FE complexity | LOW | VERIFIED | OPEN | DEFERRED | Out of scope | — | Debt | FE backlog |
| TEST-002 | Audit gap | IDOR matrix | HIGH | VERIFIED | OPEN | VERIFIED_FIXED | JWT + SQL Stage2 matrix | Stage2 suites | Broader endpoint matrix incomplete | Stage3 expand |
| TEST-003 | Gate | security-exceptions | HIGH | VERIFIED | OPEN | VERIFIED_FIXED | `audit/security-exceptions.json` | gate loader | Must renew before expires_at | Maintain file |
| OPS-001 | Gate | Gitleaks Docker | MEDIUM | VERIFIED | OPEN | BLOCKED | exit 126 in `run_full_audit.sh` | — | Official secret scan in CI Docker path | Fix CI image/runtime |
| OPS-002 | Host gitleaks | Secrets | INFO | PARTIAL | OPEN | NOT_VERIFIABLE | Host `--no-git` reported 5 leaks (needs path triage; may be fixtures) | — | Confirm not real secrets | Manual review |
| B608-* | Bandit | Dynamic SQL | MEDIUM | VERIFIED | OPEN | FALSE_POSITIVE / SAFE_IDENTIFIER_ALLOWLIST | Priority file triage; cleanup allowlist | — | Other B608 outside priority set | Selective |
| ERR-GEMINI | Audit | except Exception | MEDIUM | VERIFIED | OPEN | IMPLEMENTED_PENDING_DYNAMIC_VALIDATION | Narrowed programming errors | unit coverage limited | Transport errors still broad Exception | Optional SDK types |
| ERR-ANTHROPIC | Audit | except Exception | MEDIUM | VERIFIED | OPEN | RISK_ACCEPTED | Classify-then-retry boundary kept | — | Broad catch at API invoke | NARROW later |
| CX-* | Complexity | Extreme functions | MEDIUM | VERIFIED | OPEN | DEFERRED | See residual risks | — | Orchestrator size | Incremental extract |
| DAST-LAB | Phase policy | Dynamic AuthZ | HIGH | N/A | NOT_RUN | BLOCKED | Lab not attested this run | Stage2 unit/HTTP only | No dynamic A/B this session | Run lab DAST separately |
| FLAKE-POS-MERGE | pytest | Concurrent SQL | LOW | VERIFIED flake | — | RISK_ACCEPTED | `test_sql_concurrent_overlapping_sets` intermittent | 2/3 pass after fail | Race assertion flake | Stabilize lock/assert |
