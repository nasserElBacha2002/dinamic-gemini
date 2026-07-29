# Phase 5 — Test report

## Unit / API

```bash
cd backend && .venv/bin/python -m pytest tests/observability/test_phase5_observability.py -q --no-cov
# 9 passed
```

Related lease/health (regression):

```bash
.venv/bin/python -m pytest tests/ -k "lease_metric or job_lease or phase4_security or health_ready" -q --no-cov
# 58 passed
```

## Coverage map

| Area | Tests |
| ---- | ----- |
| Request/correlation IDs | test_http_request_id_and_metrics_endpoint |
| Route template / status class | helpers + middleware |
| Label cardinality | test_metrics_reject_high_cardinality_labels |
| Error classification / retry | test_classify_error_and_retry_policy |
| Consistency dry-run findings | test_consistency_* |
| Metrics auth | test_metrics_denied_without_auth_in_hosted |
| Lease registry bridge | test_lease_metrics_use_single_registry |

## Not claiming COMPLETED until

Full backend pytest + ruff/mypy + frontend/mobile + QG strict recorded in implementation-report.
