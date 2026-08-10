# Phase 0 — Implementation report (corrections)

## Estado

**COMPLETED** — correcciones del code review de Fase 0 aplicadas. No se inició Fase 1. No se modificó lógica productiva.

## 1. Correcciones aplicadas

1. **`scripts/audit/lib/*` incluidos:** el patrón `.gitignore` `lib/` excluía accidentalmente el paquete. Se añadió `!scripts/audit/lib/` / `!scripts/audit/lib/**`. Los cuatro módulos originales + `gate_policy.py`, `schema.py`, `artifacts.py` forman parte del cambio.
2. **Sin status stale:** `run_full_audit.sh` limpia `audit-status.json` / `audit-summary.md` al inicio; genera a temporales; publica solo tras éxito del agregador; propaga el exit del generador y del gate; no usa `|| true` sobre el agregador/gate.
3. **`run_id` + `generated_at`:** el status publicado declara correlación con la evidencia actual (`audit/raw/runs/<run_id>/`, `LATEST_RUN.txt`).
4. **Schema policy** (`lib/schema.py`): v2 aceptado; legacy (`1`/ausente) migrado solo si hay áreas/tools mínimas; incompleto / futuro / tipo inválido rechazados.
5. **Política de tools** (`lib/gate_policy.py`): única fuente de verdad para las 13 herramientas requeridas y umbrales (`allow_findings` vs hard block).
6. **Test mobile separado:** HTTPS en producción vs flags incompatibles (sin tocar lógica productiva).
7. **Artefactos:** generados ignorados en git; docs formales versionadas; `audit/raw/.gitkeep` retenido.

## 2. Archivos reales incluidos

### Paquete lib (requeridos + correcciones)
- `scripts/audit/lib/__init__.py`
- `scripts/audit/lib/statuses.py`
- `scripts/audit/lib/python_env.py`
- `scripts/audit/lib/parsers.py`
- `scripts/audit/lib/gate_policy.py`
- `scripts/audit/lib/schema.py`
- `scripts/audit/lib/artifacts.py`

### Runner / gate / docs / tests
- `scripts/audit/run_full_audit.sh`
- `scripts/audit/generate_audit_summary.py`
- `scripts/audit/enforce_quality_gate.py`
- `scripts/audit/tests/test_phase0_parsers_and_gate.py`
- `scripts/audit/tests/test_phase0_corrections.py`
- `docs/quality-gate.md`
- `.gitignore`
- `mobile/tests/fase10ProductionHardening.test.ts`
- `audit/raw/.gitkeep`
- De-indexación de outputs generados previamente trackeados (`audit/audit-status.json`, `audit/audit-summary.md`, `audit/raw/*`, `audit-results/phase-0/phase0-*.txt`)

## 3. Política de schema

| Caso | Resultado |
|------|-----------|
| `schema_version: 2` | Aceptado |
| Legacy `1` o ausente (completo) | Migrado explícitamente a v2 |
| Legacy incompleto | Rechazado |
| Versión futura / desconocida | Rechazado |
| Tipo inválido | Rechazado |

## 4. Política de outputs

| Path | Versionar |
|------|-----------|
| `audit/audit-report.md`, `audit/audit-backlog.md` | Sí |
| `audit/audit-status.json`, `audit/audit-summary.md` | No (gitignore) |
| `audit/raw/**` | No (excepto `.gitkeep`) |
| `audit-results/phase-0/phase0-*.txt` | No |
| `implementation-report.md`, `root-cause-notes.md` | Sí |

## 5. Confirmación anti-stale

Corrida `AUDIT_RUN_ID=20260728T142521Z`:

- Agregados limpiados antes de generar.
- Publicados solo tras `generate_audit_summary.py` exit 0.
- Gate leyó `run_id=20260728T142521Z` / `generated_at=2026-07-28T14:28:20+00:00`.
- Tests de integración cubren: fallo del generador (exit 7, sin status publicado) y publish con `run_id` fresco.

## 6. Comandos ejecutados y exit codes

```text
backend/.venv/bin/python -m pytest scripts/audit/tests -q --no-cov
  → 45 passed, exit 0

bash scripts/audit/run_full_audit.sh
  → schema_version=2 run_id=20260728T142521Z overall_status=findings
  → Quality Gate PASS, exit 0

backend/.venv/bin/python scripts/audit/enforce_quality_gate.py --strict
  → PASS / Deploy allowed, exit 0

backend/.venv/bin/python -m pytest -q --no-cov
  → 3797 passed, 44 skipped, exit 0

frontend: npm test -- --run
  → 203 files / 1217 tests passed, exit 0

mobile: npm test -- --watchman=false
  → core 172 + services 139 + integration 10 passed, exit 0
```

Evidencia regenerada (mismo estado final) vía `git diff HEAD` / `git status --short --untracked-files=all` en:

- `audit-results/phase-0/phase0-tooling-quality-gate-corrections-diff.txt`
- `audit-results/phase-0/phase0-tooling-quality-gate-corrections-diffstat.txt`
- `audit-results/phase-0/phase0-tooling-quality-gate-corrections-name-status.txt`
- `audit-results/phase-0/phase0-tooling-quality-gate-corrections-status.txt`

(`phase0-*.txt` están en `.gitignore` a propósito; el name-status del cambio incluye los 7 módulos `scripts/audit/lib/*`.)

## 7. Limitaciones

- Hallazgos advisory (Bandit, npm audit) se reportan y no bloquean por sí solos.
- ESLint: `errors > 0` bloquea; warnings-only permitidos.
- No se inició Fase 1.

## 8. Confirmación

**No se modificó lógica productiva** (API, workers, OCR, uploads). Solo tooling de auditoría/quality gate + test mobile de config + `.gitignore`.
