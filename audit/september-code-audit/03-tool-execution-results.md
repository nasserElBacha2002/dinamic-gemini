# 03 — Tool execution results

`run_id` oficial: **20260914T152649Z**  
Logs: `audit/september-code-audit/tool-logs/`  
Raw: `audit/raw/` (+ snapshot `audit/raw/runs/20260914T152649Z`)

## A. `bash scripts/audit/run_full_audit.sh`

| Campo | Valor |
|-------|-------|
| Directorio | repo root |
| Inicio | 2026-09-14T15:26:49Z |
| Duración | ~333.6 s (`real 333.61`) |
| Exit code | **1** |
| Resultado | **FAIL** (gate) |
| Interpretación | Collectors ejecutados; agregador publicó status; `enforce_quality_gate.py --strict` falló |

### Motivos del gate (VERIFIED, log)

- Gitleaks: `EXECUTION_ERROR` (exit 126)
- `security-exceptions.json` missing
- `overall_status=error`

### Sub-resultados (desde `audit-summary.md` / exitcodes)

| Tool | Exit / status | Clasificación |
|------|---------------|---------------|
| Ruff | 0 / OK | PASS |
| Mypy | 0 / OK | PASS |
| Pytest | 0 / OK — 5261 passed, 4 skipped | PASS |
| Bandit | 1 / FINDINGS — 0 high, 102 medium, 72 low | PASS_WITH_WARNINGS |
| pip-audit | 0 / OK — 0 vulns | PASS |
| Gitleaks (Docker) | 126 / EXECUTION_ERROR | **BLOCKED** |
| FE typecheck | 0 | PASS |
| FE vitest | 0 — 1300 passed | PASS |
| FE eslint | 0 problems as errors; 26 warnings | PASS_WITH_WARNINGS |
| FE npm audit | 1 / FINDINGS — 2 moderate | PASS_WITH_WARNINGS |
| Mobile typecheck | 0 | PASS |
| Mobile lint | 0 | PASS |
| Mobile jest | 0 — 734 passed | PASS |
| Mobile npm audit | 1 / FINDINGS — 1 critical, 13 high | PASS_WITH_WARNINGS (gate progressive) / **FAIL** si se exige high=0 |
| BE architecture | FINDINGS (boundaries fail=2) | PASS_WITH_WARNINGS |
| FE architecture | FINDINGS; jscpd NOT_INSTALLED | PASS_WITH_WARNINGS |

## B. Host gitleaks (fallback)

| Campo | Valor |
|-------|-------|
| Comando | `gitleaks detect --source . --config .gitleaks.toml --redact --report-path audit/september-code-audit/tool-logs/gitleaks-host-report.json --report-format json` |
| Versión | 8.30.1 |
| Exit | **0** |
| Resultado | **PASS** — `no leaks found` (~49.5 MB, 1107 commits) |
| Warnings | Invalid `.gitleaksignore` fingerprint for example GCP file |
| Nota | No es el collector Docker pinned; documentado como evidencia alternativa |

## C. npm audit high (manual paralelo)

| Target | Exit | Resultado |
|--------|------|-----------|
| `frontend` `npm audit --audit-level=high` | 0 | PASS (2 moderate only) |
| `mobile` `npm audit --audit-level=high` | 1 | **FAIL** — 40 vulns (1 critical `tar`, 13 high) |

## D. No ejecutados (justificación)

| Tool | Clasificación | Motivo |
|------|---------------|--------|
| Docker gitleaks oficial (reintento unsandboxed) | BLOCKED | docker.sock permission denied en entorno agente |
| `security-agents` + Semgrep/OSV/CodeQL/Trivy SAST | NOT_CONFIGURED | CLI no en repo |
| DAST suites (`security-audit.yaml`) | NOT_RUN | Requiere API local + tokens + DB disposable; fase 1 prohíbe DAST contra deploy |
| `scripts/release/run_security_scanners.sh` | NOT_RUN | Docker + network pesado; gitleaks host ya cubre secretos parcialmente |
| Smoke/e2e/migration drills | NOT_RUN | SQL Server disposable requerido |
| `scripts/quality_gate.sh` completo | NOT_RUN | Cubierto por full audit collectors equivalentes |

## E. Efectos colaterales de herramientas

| Efecto | Detalle |
|--------|---------|
| Escritura `audit/raw/**` | Esperado |
| `audit/audit-status.json`, `audit/audit-summary.md` | Regenerados (gitignored típico) |
| `htmlcov/` | Regenerado por pytest |
| Código productivo | **Sin cambios** |
| Solo artefactos nuevos versionables esperados | `audit/september-code-audit/**` |
