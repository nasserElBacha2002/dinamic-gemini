# Phase 7 — Feature flag report

| Flag / setting | Default | Consumer | Production | Action |
| -------------- | ------- | -------- | ---------- | ------ |
| `EXTERNAL_FALLBACK_PER_IMAGE_ENABLED` | false | start_aisle_processing | optional | KEEP — owner: platform; requires supplier prompt when on |
| `EXTERNAL_FALLBACK_MODE` | GLOBAL_BATCH | fallback orchestrator | GLOBAL_BATCH | KEEP; PER_ASSET deprecated |
| `RECOVERY_*` / stale recovery scheduler enable | off | StaleJobRecoveryScheduler | opt-in | KEEP |
| `METRICS_MAX_SERIES_PER_METRIC` | 500 | MetricsRegistry | on | KEEP |
| Repository backend SQL vs memory | SQL hosted | AppContainer | SQL | KEEP |
| Identification mode hierarchy | INTERNAL_OCR default | resolver | on | KEEP |
| Flags disabling fencing / tenant scope | — | — | forbidden | none present as kill-switches |

No dead flags removed this phase (all inspected flags have consumers). No security/fencing bypass flags retained.
