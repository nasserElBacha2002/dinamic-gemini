# Phase 7 — Legacy removal report

## Removed (executable)

None in this slice. No legacy executable path met REMOVE evidence (wiring + tests + no consumers).

## Deprecated

| Item | Replacement | Sunset |
| ---- | ----------- | ------ |
| `python -m scripts.ops.reconcile_aisle` | `inspect_aisle` | 2026-12-31 |
| `EXTERNAL_FALLBACK_MODE=PER_ASSET` | `GLOBAL_BATCH` | after GLOBAL_BATCH soak (existing note) |
| Floating `python:3.11-slim` base tag | digest-pinned base | next infra release |

## Conserved (required)

- Historical `LEGACY_LLM` job snapshots (read / retry-of-historical).
- New jobs continue to reject effective `LEGACY_LLM` at start.
- Memory adapters for tests / local repository mode.
- OCR and CODE_SCAN runtime dependencies in Docker images.
- Admin API `reconcile_aisle` recovery operation (not the CLI alias).

## Policy restated

```text
nuevos jobs no usan LEGACY_LLM
```
