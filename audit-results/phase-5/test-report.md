# Phase 5 — Test report (corrections)

## Focused

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/observability \
  backend/tests/integration/recovery \
  -q --no-cov
```

Result (latest corrections run): **24 passed** (includes SQL recovery when SQL available).

Coverage includes:

- Histogram golden / series limit / unmatched cardinality
- Logging forging / correlation helpers
- RecoverStaleJob memory + SQL concurrent

## Alerts

```bash
promtool check rules deploy/prometheus/dinamic-phase5-alerts.yml
promtool test rules deploy/prometheus/tests/phase5_alerts.test.yml
```

(Use Docker `prom/prometheus` if `promtool` is not on PATH.)

## Full gate

Run full backend pytest, ruff, mypy, frontend/mobile, security scans, and `enforce_quality_gate.py --strict` before merge. See corrections deliverables for latest run artifacts.
