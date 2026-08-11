# Phase 6 — Final cleanup notes

**Date:** 2026-08-11
**Canonical docs:** `audit/db-integrity-final-architecture.md`, `audit/db-integrity-final-validation.md`

## Productive changes (minimal)

| Change | Classification |
| ------ | -------------- |
| `Inventory.mark_processing` / `mark_failed` clear `completed_at` | Writer hygiene aligned with reconciler; not a DB CHECK |
| Domain test for leave-COMPLETED clears `completed_at` | Coverage |
| Position / finalization test stubs + `ExplicitInventoryCompareAndSet` | Phase 3 CAS contract hygiene (stubs missing CAS) |
| Final architecture + validation markdown | Documentation |

## Decisions

| Item | Decision |
| ---- | -------- |
| `completed_at` CHECK | **NO_ACTION** (follow-up CLOSED) |
| New migrations | **0** |
| SP / Trigger | Remain **0** |
| NoopRepo + `ExplicitInventoryCompareAndSet` | **KEEP_WITH_REASON** — stub implements `InventoryRepository` ABC |
| Test CAS helpers under `tests/` only | Confirmed; not imported from `src/` |

## Temporary debt scan (touched modules)

| Item | Class |
| ---- | ----- |
| `reconcile() -> bool` False ambiguity | KEEP_WITH_REASON (documented; callers best-effort) |
| `sql_batch` hasattr/fast_executemany restore | KEEP_WITH_REASON (driver capability) |
| Package repo `# type: ignore[attr-defined]` on `begin_transaction` | KEEP_WITH_REASON (client protocol) |
| Phase evidence `*-diff.txt` dumps | OUT_OF_SCOPE (gitignored / not for commit) |

No REMOVE_NOW dead production paths found that were safe to delete without caller risk.
