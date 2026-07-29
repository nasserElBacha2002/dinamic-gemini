# Phase 7 — Smoke test report

Command:

```bash
bash scripts/release/run_smoke_tests.sh
```

Covers:

- App import + `GET /health` + `GET /ready` via TestClient
- Ops CLI `--help` for recover/inspect/preflight
- Pytest: health/ready, recovery, fencing characterization

Destructive production calls: **none**.
