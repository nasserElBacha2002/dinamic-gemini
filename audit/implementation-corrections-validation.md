# Implementation corrections validation — P1 positioning semantics

**Date:** 2026-08-05  
**Task:** corrections-scoped P1 (sequence event semantics)  
**Final status:** `CORRECTIONS_WITH_WARNINGS` (large diff file/line thresholds; scope controlled)

## Explicit confirmation

**P2 association algorithm was NOT implemented.** No root-cause association fix was shipped. Server evidence pack remains `BLOCKED_PENDING_SERVER_EXECUTION` with PENDING result tables. No invented server SQL results.

## Architectural decisions

1. **Classifier module** (`sequence_event_classifier.py`): owns event kinds, reason codes, status normalization, multi-detection reduction, and messages. `warnings_builder.py` only builds operational warnings.
2. **Identity = `position_label_id` only.** `position_label_name` is descriptive snapshot; VALID/LEGACY without id → `POSITION_LABEL_UNRESOLVED` + `MISSING_POSITION_ID`.
3. **LABEL_RESOLVED ≠ TRANSITION_APPLIED.** Sequence use case passes `reconciler_transition_applied=False` because there is no persisted SET_POSITION ledger in P1. Resolved labels return `POSITION_LABEL_RESOLVED` / “Etiqueta de posicionamiento resuelta”.
4. **Gap (documented, not migrated):** persisting reconciler transition evidence is a separate task if product requires `POSITION_TRANSITION_APPLIED` in production responses.
5. **`detections_count`** remains total persisted detections. Warnings use `resolved_detections_count` parameter. Public DTO does **not** add `resolved_detections_count` / `unresolved_detections_count` (compatibility preserved).
6. **Additive sequence fields:** `reason_code`, `position_label_id` on frame DTO (optional for older clients).
7. **Frontend:** keep established per-module `API_BASE` + `apiRequestJson` pattern (same as other APIs). Explicit enum labels; unknown → neutral message.
8. **P0 pack:** SQL templates with confirmed schema (`job_source_assets.original_filename`, `@inv` via aisle/detections.inventory_id, JOIN `client_position_labels`); not labeled as executed evidence.

## Residual risks

- Until a transition ledger exists, UI will show “Etiqueta de posicionamiento resuelta” rather than “Evento de transición…” even when reconciler did apply SET_POSITION offline.
- P2 association for unresolved priority assets remains blocked on server SQL evidence.
- Frontend lint reports pre-existing warnings unrelated to this patch (0 errors).

## Validation commands and results

### Backend unit / use-case / contract tests

```bash
cd <repo>
.venv/bin/pytest backend/tests/unit/positioning_operational/ -q --tb=short
```

- **Exit code:** 0  
- **Tests:** 47 passed  

### Backend lint (ruff)

```bash
cd backend
../.venv/bin/ruff check src/application/services/positioning_operational \
  src/application/use_cases/positioning_operational \
  src/api/schemas/positioning_operational_schemas.py \
  src/domain/positioning_operational/entities.py \
  tests/unit/positioning_operational
```

- **Exit code:** 0  
- **Result:** All checks passed

### Backend format (black)

```bash
../.venv/bin/black --check \
  src/application/services/positioning_operational/sequence_event_classifier.py \
  src/application/services/positioning_operational/warnings_builder.py \
  src/application/use_cases/positioning_operational/get_aisle_positioning_sequence.py \
  src/application/use_cases/positioning_operational/get_aisle_operational_view.py
```

- **Exit code:** 0  
- **Result:** 4 files would be left unchanged

### Backend type checking (mypy)

```bash
cd backend
../.venv/bin/mypy \
  src/application/services/positioning_operational/sequence_event_classifier.py \
  src/application/services/positioning_operational/warnings_builder.py \
  src/application/use_cases/positioning_operational/get_aisle_positioning_sequence.py \
  src/application/use_cases/positioning_operational/get_aisle_operational_view.py \
  src/api/schemas/positioning_operational_schemas.py \
  src/domain/positioning_operational/entities.py
```

- **Exit code:** 0  
- **Result:** Success: no issues found in 6 source files  
- Note: run from `backend/` so mypy uses package roots correctly (repo-root path can pull unrelated stub gaps like `pyodbc`).

### Frontend typecheck

```bash
cd frontend && npm run typecheck
```

- **Exit code:** 0

### Frontend lint

```bash
cd frontend && npm run lint
```

- **Exit code:** 0  
- **Result:** 0 errors, 22 pre-existing warnings (unrelated files)

### Frontend tests (scoped)

```bash
cd frontend && npm run test -- --run tests/api/positionLabelDetectionsApi.test.ts
```

- **Exit code:** 0  
- **Tests:** 4 passed

### Frontend production build

```bash
cd frontend && npm run build
```

- **Exit code:** 0  
- **Result:** build OK; dist secrets scan OK

## Files modified/created (this correction)

See `audit/implementation-corrections-status.txt` and `audit/implementation-corrections-diffstat.txt`.

## Git inspection

```bash
git add -N .
git --no-pager status --short
git --no-pager diff --stat
```

- Staged changes: none  
- Unstaged: 16 files, +1707 / −83 (includes tests + P0 pack + classifier)
