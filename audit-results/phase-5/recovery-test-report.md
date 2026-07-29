# Phase 5 — Recovery test report

| Scenario | Result |
| -------- | ------ |
| Consistency: RUNNING without lease | unit pass |
| Consistency: expired lease → AUTO_RECOVERY | unit pass |
| Metrics registry rejects job_id label | unit pass |
| Lease metrics single registry | unit pass |
| Retry exhausted / auth not retryable | unit pass |
| Request ID echoed + /metrics open in test | unit pass |
| /metrics denied hosted without key | unit pass |
| Duplicate stale reclaim CAS | covered by existing Phase 1/3 SQL/memory reclaim tests (one winner) |
| Active lease refuses recover_job | CLI logic + unit consistency |

SQL reclaim idempotency remains validated by prior phase suites (`test_sql_atomic_job_claim`, lease fencing). Phase 5 does not change stale-fail CAS semantics.
