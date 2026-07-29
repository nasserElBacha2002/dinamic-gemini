# Phase 7 — Cleanup matrix

| Candidate | Area | Evidence | Dynamic? | Class | Notes |
| --------- | ---- | -------- | -------- | ----- | ----- |
| `LEGACY_LLM` for new jobs | backend | reject path | no | KEEP | Historical read required |
| `scripts.ops.reconcile_aisle` | scripts | stderr DEPRECATED + test | no | DEPRECATE | Sunset **2026-12-31**; ticket PHASE7-CLEANUP-RECONCILE-AISLE; consumer=runbooks; owner=ops; metric=stderr log line |
| `scripts.ops.inspect_aisle` | scripts | canonical | no | KEEP | |
| `scripts.ops.recover_job` | scripts | use case | no | KEEP | |
| Memory repositories | infra | tests + AppContainer | no | KEEP | Hosted SQL |
| OCR / CODE_SCAN | pipeline | Docker verify scripts | no | KEEP | Out of Phase 7 functional change |
| Floating `python:3.11-slim` | docker | Dockerfiles | n/a | REMOVE | Replaced by digest pin |
| Migration 0001–0073 | DB | apply chain | n/a | KEEP | Never squash |
| Physical column drops | DB | unknown readers | n/a | MIGRATE_FIRST | Post-release |

## REMOVE count

**REMOVE=1** (floating Docker base tag → digest). No unsafe mass deletion of wired code. Remaining KEEP rows justified by runtime wiring / tests / historical read paths.
