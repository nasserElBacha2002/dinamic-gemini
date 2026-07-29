# Phase 4 — Implementation report

## 1. Estado

`COMPLETED` (with documented temporary exceptions; Quality Gate strict **PASS**).

## 2. Alcance

Seguridad transversal: dependencias, backend hardening, frontend/mobile hygiene, Docker/CI, logging redaction, tests, documentación. **No** se inició Fase 5. Fases 0–3 no se reabrieron arquitectónicamente (solo alineación de tests a fencing Phase 3).

## 3. Metodología

1. Inventario + scanners (`pip_audit`, `bandit`, `npm audit` FE/mobile).
2. Matriz de vulnerabilidades con reachability.
3. Correcciones mínimas de riesgos High/Medium alcanzables.
4. Excepciones temporales con owner + expiry.
5. Validación completa + Quality Gate `--strict`.

## 4–8. Findings

Ver `vulnerability-matrix.md` y `security-exceptions.md`.

**Critical/High alcanzables corregidos:** Docker root (P4-001), API_KEY vacío en prod-like (P4-002).

**Aceptados temporalmente:** FE localStorage JWT (P4-003), Actions tags (P4-009), RR6 moderate (P4-010), Expo transitive (P4-011), health detail (P4-013), upload size defaults (P4-014).

**Falsos positivos:** Bandit B608 SQL f-strings con binds (P4-020).

## 9. Dependencias actualizadas

Ninguna bump de runtime Python (pip_audit limpio). FE/mobile: sin `audit fix --force`; majors diferidos.

## 10. Breaking changes evitados

- Sin React Router 7 / Expo major.
- Sin rediseño auth a httpOnly cookies.
- CORS: rechazo de `*` solo cuando credentials=true (comportamiento inseguro previo).

## 11–21. Hardening por área

| Área | Cambio |
| ---- | ------ |
| Backend | CORS allowlists, security headers, API key hash+compare_digest, API_KEY required prod-like, TrustServerCertificate env-gated, redaction SAS/JWT |
| Frontend | Test higiene VITE_*; localStorage documentado |
| Mobile | SecureStore ya en uso; logging con redaction (tests existentes) |
| Uploads | Controles previos retenidos; límites documentados |
| SQL | Sin SQLi demostrable; B608 FP |
| SSRF | Sin sinks URL controlables nuevos |
| Auth | JWT HS256; API key hardened |
| Tenant | Phase 2 policies intactas |
| Secrets | `.dockerignore` + redaction |
| Logging | Patrones SAS/JWT |
| Docker | `USER appuser` uid 10001 |
| CI/CD | `contents: read` ya presente; SHA pin diferido |

## 22. Excepciones

`security-exceptions.md` (expiran 2026-10-17 / 2026-12-17).

## 23–25. Tests / Scanners / QG

- Backend pytest: **3962 passed**, 16 skipped
- Frontend: typecheck/lint/test/audit-high **PASS**
- Mobile: typecheck/lint/test **PASS**
- pip_audit: **0 vulns**
- Bandit: FINDINGS allowed (0 High bloqueantes en política)
- `enforce_quality_gate.py --strict`: **PASS**

## 26. Migraciones

Ninguna.

## 27. Rollback

Revertir commits de Phase 4; Docker vuelve a root; CORS vuelve a métodos `*`. Sin migración DB.

## 28. Riesgos restantes

Rate limiting distribuido, httpOnly cookies, Expo upgrade, Actions SHA pins, CSP estricto en hosting FE.

## 29–30. Confirmaciones

- Phase 5 **no** iniciada.
- Mergeable a `main` tras review (QG PASS).
