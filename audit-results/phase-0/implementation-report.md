# Phase 0 — Implementation report

## 1. Causas raíz encontradas

1. **Backend NOT_RUN:** `run_backend_audit.sh` usaba `command -v` sobre PATH sin activar `backend/.venv`.
2. **TypeScript falsos errores:** `findall(error TS\d+:)` ignoraba exit code y el resumen `Found N errors`.
3. **Gate ciego:** `failed` ausente se trataba como 0 → “tests OK” aunque no hubieran corrido.
4. **Vitest parse miss → OK:** sin resumen se marcaba OK.
5. **Mobile ausente** del pipeline `run_full_audit.sh`.
6. **Vocabulario inconsistente:** `NOT_INSTALLED` (shell) vs `NOT_RUN` (agregador).

## 2. Archivos modificados / creados

### Nuevos
- `scripts/audit/lib/statuses.py`
- `scripts/audit/lib/python_env.py`
- `scripts/audit/lib/parsers.py`
- `scripts/audit/lib/__init__.py`
- `scripts/audit/resolve_python.sh`
- `scripts/audit/run_mobile_audit.sh`
- `scripts/audit/tests/test_phase0_parsers_and_gate.py`
- `audit-results/phase-0/root-cause-notes.md`
- `audit-results/phase-0/implementation-report.md`

### Modificados
- `scripts/audit/run_backend_audit.sh`
- `scripts/audit/run_frontend_audit.sh`
- `scripts/audit/run_full_audit.sh`
- `scripts/audit/generate_audit_summary.py`
- `scripts/audit/enforce_quality_gate.py`
- `docs/quality-gate.md`
- `mobile/tests/fase10ProductionHardening.test.ts` (HTTPS en caso production; no oculta fallo)

## 3. Diseño implementado

- Estados: `OK | FINDINGS | EXECUTION_ERROR | PARSE_ERROR | NOT_AVAILABLE | NOT_RUN | SKIPPED`
- Sidecars `*.exitcode` junto a reportes raw
- Resolución Python: `AUDIT_PYTHON` → venvs del repo → `VIRTUAL_ENV` → fallback
- Parsers preferentes de formato estructurado / resúmenes oficiales
- Mobile como área de primera clase
- `schema_version: 2` en `audit-status.json`
- Gate estricto falla si tooling inválido o required tools no ejecutados

## 4. Schema

```json
{
  "schema_version": 2,
  "parser_version": "phase0-2.0.0",
  "areas": {
    "<area>": {
      "tools": {
        "<tool>": {
          "status": "...",
          "exit_code": 0,
          "error": null,
          "parser": "...",
          "parser_version": "..."
        }
      },
      "highlights": {
        "pytest_failed": 0,
        "vitest_failed_tests": 0,
        "jest_failed": 0
      }
    }
  }
}
```

## 5. Mobile

- `run_mobile_audit.sh`: typecheck, lint, `npm test -- --watchman=false`, npm audit
- Incluido en `run_full_audit.sh` y en el gate estricto

## 6. Tests agregados

`scripts/audit/tests/test_phase0_parsers_and_gate.py` — 25 casos (pytest/ruff/mypy/tsc/vitest/jest/npm audit/gate).

## 7–8. Comandos y resultados (validación)

```text
backend/.venv/bin/python -m pytest scripts/audit/tests/ → 25 passed
bash scripts/audit/run_backend_audit.sh
  Python: backend/.venv/bin/python
  Ruff OK, Mypy OK, Bandit FINDINGS, pip-audit OK, Pytest OK (3797 passed, 44 skipped)
bash scripts/audit/run_frontend_audit.sh
  ESLint OK(exit0)/warnings parsed, Typecheck OK (ts_errors=0), Vitest OK (1217), npm audit FINDINGS
bash scripts/audit/run_mobile_audit.sh
  Typecheck OK, Lint OK, Jest OK, npm audit FINDINGS (reported, not remediated)
backend/.venv/bin/python scripts/audit/generate_audit_summary.py → schema_version=2
backend/.venv/bin/python scripts/audit/enforce_quality_gate.py --strict → PASS / Deploy allowed
```

Backend ya no aparece como `NOT_RUN`. Typecheck ya no inventa miles de errores.

## 9. Limitaciones

- Auditorías heurísticas de arquitectura pueden seguir marcando `FINDINGS` (no bloquean por sí solas salvo `overall_status=error`).
- `npm audit` mobile/frontend puede reportar FINDINGS (vulnerabilidades) — Phase 0 solo reporta, no remedia.
- Full audit end-to-end depende del tiempo de pytest/vitest/jest.

## 10. Riesgos pendientes

- CI GitHub Actions aún no invoca `run_full_audit.sh` (gate local distinto del workflow develop).
- Compatibilidad de reportes históricos sin `schema_version` (gate los acepta como legacy).

## 11. Confirmación

**No se modificó lógica productiva** (API, workers, OCR, uploads, source of truth). Solo tooling de auditoría/quality gate (+ un test mobile de config).
