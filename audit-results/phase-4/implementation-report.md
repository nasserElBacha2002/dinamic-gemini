# Phase 4 — Implementation report

## 1. Estado

`COMPLETED` after Phase 4 **corrections** (Model A API key, SQL TLS fail-safe, structured exceptions, gitleaks, Bandit `blocking_high`, CORS hosted, Docker smoke path). Quality Gate strict **PASS** (`run_id=20260729T125650Z`).

## 2. Alcance

Seguridad transversal: dependencias, backend hardening, frontend/mobile hygiene, Docker/CI, logging redaction, tests, documentación. **No** se inició Fase 5. Fases 0–3 no se reabrieron arquitectónicamente.

## 3. Metodología

1. Inventario + scanners (`pip_audit`, `bandit`, `npm audit` FE/mobile, **gitleaks**).
2. Matriz de vulnerabilidades con reachability.
3. Correcciones de blockers de code review (ver `corrections-report.md`).
4. Excepciones **estructuradas** (`audit/security-exceptions.json`) con owner + expiry.
5. Validación completa + Quality Gate `--strict`.

## 4–8. Findings

Ver `vulnerability-matrix.md` y `security-exceptions.md`.

**Critical/High alcanzables corregidos / re-diseñados:** Docker root (P4-001), API key Model A (no secreto embebido en browser), SQL TLS hosted default `TrustServerCertificate=no`.

**Aceptados temporalmente (JSON SoT):** FE localStorage JWT (P4-003), Actions tags (P4-009), RR6 moderate (P4-010), Expo transitive (P4-011), health detail (P4-013), upload size defaults (P4-014).

**Falsos positivos:** Bandit B608 SQL f-strings con binds (P4-020).

## 9. Dependencias actualizadas

Ninguna bump de runtime Python (pip_audit limpio). FE/mobile: sin `audit fix --force`; majors diferidos. Reachability mobile: `mobile-dependency-reachability.md`.

## 10. Breaking changes evitados

- Sin React Router 7 / Expo major.
- Sin rediseño auth a httpOnly cookies (P4-003).
- Sin API key embebida en frontend/mobile.

## 11–21. Hardening por área

| Área | Cambio |
| ---- | ------ |
| Backend | CORS hosted HTTPS-required; security headers; API key path-scoped (Model A); SQL TLS fail-safe; redaction SAS/JWT structure-preserving |
| Frontend | VITE hygiene test + **post-build** `scan-dist-secrets.cjs` |
| Mobile | SecureStore; reachability matrix for Critical/High tooling |
| Uploads | Controles previos retenidos |
| SQL | Hosted default no trust; full connection string validation |
| Auth | JWT para clientes públicos; API key solo prefixes internos |
| Secrets | gitleaks (Docker digest pin) + `.dockerignore` + redaction |
| Docker | non-root uid 10001; `COPY --chown`; smoke script |
| Exceptions | `audit/security-exceptions.json` + QG schema/expiry |
| CI/CD | Raw scanner outputs gitignored; artifacts under `audit/raw/<run_id>` |

## 22. Excepciones

SoT: `audit/security-exceptions.json`. Generated: `security-exceptions.md`. Gate fails on expiry/invalid schema.

## 23–25. Tests / Scanners / QG

- Backend pytest (full audit suite): **PASS**
- Frontend / Mobile (via `run_full_audit.sh`): **PASS**
- pip_audit: **OK**
- Bandit: FINDINGS allowed; **blocking_high** gate metric
- Gitleaks: **OK** (0 secrets)
- `enforce_quality_gate.py --strict`: **PASS** (`run_id=20260729T125650Z`)

## 26. Migraciones

Ninguna.

## 27. Rollback

Revertir commits de Phase 4 + corrections; Docker vuelve a root; CORS/API key/SQL TLS policies revierten. Sin migración DB.

## 28. Riesgos restantes

Rate limiting distribuido, httpOnly cookies (P4-003), Expo major (P4-011), Actions SHA pins (P4-009), CSP estricto en hosting FE.

## 29–30. Confirmaciones

- Phase 5 **no** iniciada.
- Mergeable a `main` tras review (QG PASS + acceptance criteria de corrections).
