# Phase 0 — Root-cause notes (pre-implementation)

## Why backend appears as NOT_RUN
`run_backend_audit.sh` uses `command -v ruff|mypy|pytest` on PATH without activating
`backend/.venv`, root `.venv`, or `venv`. When tools are only in the project venv,
reports say "no instalado" → aggregator maps to `NOT_RUN` → area `NOT_RUN`.
`enforce_quality_gate.py` then treats missing `failed` as 0 → "Backend tests: OK".

## Why TypeScript can produce false errors
`parse_frontend_typecheck` counts every `error TS\d+:` via `findall`, ignores tsc
exit code, and ignores the "Found N errors" summary. Inflated counts (e.g. 2572)
appear even when the real failure is tooling/noise.

## Python interpreter selection
Bare `python3` / PATH binaries. No `AUDIT_PYTHON`, no venv preference, no
`python -m pytest`.

## Backend tool execution
`ruff`/`mypy`/`bandit`/`pip-audit`/`pytest` invoked if on PATH; shell always exits 0.

## Mobile
Not part of `run_full_audit.sh`. Jest already uses `--watchman=false` in package.json.

## Watchman
Metro DX only (`with-metro-env.sh`). Not required for mobile Jest in verify/audit.

## Status semantics (before)
Shell: OK / FINDINGS / ERROR / NOT_INSTALLED / SKIPPED.
Aggregator: OK / FINDINGS / ERROR / NOT_RUN / SKIPPED. "no instalado" → NOT_RUN.
Vitest parse miss → OK with empty metrics.

## enforce_quality_gate.py
Reads only `audit/audit-status.json`. Uses failed counts (defaults to 0),
`max_severity==critical`, `overall_status==error`. Blind to NOT_RUN.

## Raw vs aggregate inconsistencies
Shell status discarded by parsers; Vitest ERROR→OK; TypeScript overcount;
highlights.pytest_failed never written; NOT_INSTALLED ≠ NOT_RUN vocabulary.
