# Final findings register (post-corrections)

**Overall status:** `REMEDIATION_PARTIALLY_COMPLETED`

| Finding ID | Fuente | Categoría | Severidad original | Certeza | Estado anterior | Estado final | Evidencia | Tests | Riesgo residual | Decisión |
|------------|--------|-----------|--------------------|---------|-----------------|--------------|-----------|-------|-----------------|----------|
| SEC-001 | Internal | AuthZ inventories list/get/export | HIGH | VERIFIED | OPEN | VERIFIED_FIXED | InventoryAccessPolicy + scoped list/get/soft-delete | Stage2 UC/HTTP/JWT/SQL | Other inventory nested routes | Keep Stage3 |
| SEC-002 | Internal | AuthZ clients list/get | HIGH | VERIFIED | OPEN | VERIFIED_FIXED | ClientAccessPolicy | Stage2 suites | Nested client children beyond Stage2 | Stage3 |
| SEC-TENANT-EXTRA | Stage2 scope | Additional tenant routes | HIGH | PARTIAL | OPEN | PARTIALLY_IMPLEMENTED_PENDING_DAST | Priority routes only | Partial matrix | ~140 endpoints without dynamic proof | Matrix doc |
| TEST-002 | Audit gap | IDOR matrix | HIGH | VERIFIED | claimed FIXED | PARTIALLY_IMPLEMENTED_PENDING_DAST | Stage2 matrix ≠ full surface | JWT/SQL Stage2 | No DAST | Honest partial |
| SEC-003 | Internal | Refresh in-memory | HIGH | VERIFIED | OPEN | DEFERRED | Unchanged | — | Multi-instance | Product |
| SEC-004 | Internal | FE JWT storage | MEDIUM | VERIFIED | OPEN | RISK_ACCEPTED | Unchanged | — | XSS | FE backlog |
| SEC-005 | Internal | OpenAPI defaults | MEDIUM | VERIFIED | OPEN | DEFERRED | Unchanged | — | Info surface | Ops |
| SEC-006 | npm mobile | Deps | HIGH | advisory | OPEN | RISK_ACCEPTED | security-exceptions.json | npm audit | Transitive | Expires 2026-12-15 |
| SEC-007 | npm FE | Deps | LOW | VERIFIED | OPEN | RISK_ACCEPTED | vitest mocker | npm audit | Dev-only | Expires 2026-12-15 |
| ARCH-001 | Arch | Domain→pipeline | MEDIUM | VERIFIED | OPEN | VERIFIED_FIXED | Constant in domain | architecture tests | — | Closed |
| ARCH-002 | Arch | Application→api | MEDIUM | VERIFIED | OPEN | VERIFIED_FIXED | application schemas | architecture tests | — | Closed |
| SQL-SOFT-DELETE-UOW | Adversarial | Partial commit | HIGH | VERIFIED | OPEN | VERIFIED_FIXED | Consistency error after write; mid-UPDATE fault tests | SQL Stage2 | — | Closed |
| FLAKE-POS-MERGE | pytest | Concurrent merge | MEDIUM | VERIFIED | OPEN | VERIFIED_FIXED | Assertion fixed; deadlock→conflict; aisle lock+HOLDLOCK | 40/40 overlapping | — | Closed |
| OPS-001 | Gate | Gitleaks Docker | MEDIUM | VERIFIED | OPEN | BLOCKED | exit 126 historically | — | CI Docker path | Tooling |
| GITLEAKS-HOST | Host scan | Secrets | — | VERIFIED | NEEDS_TRIAGE | TRIAGED | Allowlists + ignore fix; 0 leaks with config | gitleaks rerun | Local gitignored SA json | See triage doc |
| SEMGREP | SAST | Static | — | — | NOT_VERIFIABLE | EXECUTED_LOCAL_RULESET | Local yaml; p/python blocked by proxy | 0 findings local | Registry download blocked | Formal note |
| DAST | Policy | Dynamic | HIGH | N/A | BLOCKED_BY_ENVIRONMENT | BLOCKED_BY_ENVIRONMENT | Lab not attested | — | No dynamic A/B | Keep blocked |
| TRIVY/OSV | SAST | OS/deps | — | — | NOT_RUN | NOT_RUN | Not configured here | — | — | Explicit |
| CX-* | Complexity | Extreme fns | MEDIUM | VERIFIED | DEFERRED | DEFERRED | Unchanged | — | Orchestrator size | Backlog |
