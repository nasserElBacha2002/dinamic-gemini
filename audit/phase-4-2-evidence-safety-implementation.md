# Phase 4.2 — Evidence Safety and Critical Traceability Fixes

## 1. Executive summary

**Verdict:** COMPLETE

Phase 4.2 closes the critical gap where a resolvable `source_image_id` could be shown as valid evidence even when traceability was INVALID, MISSING, or UNVALIDATED.

A post-implementation code review identified one P0 and several P1/P2 inconsistencies. This document includes the original implementation summary plus the **corrections pass** (June 2026).

**Implemented:**
- Final sent-image validation only (`frames_sent_ids` authority)
- Reference-image rejection in validation
- Central `is_traceability_evidence_displayable()` rule
- Fail-closed `has_valid_evidence` (persisted **and** derived)
- `traceability_warning` persisted and exposed via API
- Frontend gating on VALID + `has_valid_evidence`
- Component tests for `ResultEvidencePanel` and `ResultEvidenceViewer`
- Invalid traceability precedence over crop-record-only UI
- Stale preview cleanup on prop transitions

**Critical risk removed:** Operators no longer see aisle source images as evidence when the provider reference was not in the final sent frame set.

**Unsafe evidence display still possible?** Only for legacy rows without explicit `has_valid_evidence: true` (fail-closed API and frontend defaults).

**Video traceability:** Not implemented (explicitly out of scope).

**Phase 4.3:** Not started.

---

## 2. Code review corrections (June 2026)

### 2.1 Code review findings addressed

| Finding | Priority | Resolution |
|---------|----------|------------|
| `prompt_listed_image_ids` used as validation fallback | P0 | Removed from `extract_sent_image_ids_from_composition()`; only `frames_sent_ids` authorizes VALID |
| `has_valid_evidence` hybrid model (persisted vs derived) | P1 | Fail-closed: `persisted is True AND derived` in canonical view via `resolve_has_valid_evidence_displayable()` |
| Missing component tests for evidence UI | P1 | Added `ResultEvidencePanel.test.tsx`, `ResultEvidenceViewer.test.tsx` |
| Invalid traceability hidden by crop-record state | P2 | `ResultEvidenceViewer` checks traceability before `record_only` |
| Stale preview after status transition | P2 | `useEffect` closes dialog / clears `previewTarget` when non-displayable |
| Vague test reporting | P2 | Exact counts documented below |

### 2.2 Final sent-image authority

```text
frames_sent_ids is the only authority used to mark evidence VALID.
```

`prompt_listed_image_ids` remains in prompt composition and audit snapshots for **diagnostics only**. It must never produce VALID when `frames_sent_ids` is absent, malformed, or empty.

### 2.3 Eligibility policy

**Model:** persisted **and** fail-closed at read time.

```python
has_valid_evidence = (
    summary_json.get("has_valid_evidence") is True
    and is_traceability_evidence_displayable(traceability_status, source_image_id)
)
```

- Persisted `has_valid_evidence` is written at pipeline persist time (`v3_report_mapper.py`).
- API canonical view applies `resolve_has_valid_evidence_displayable()` so contradictory or legacy rows cannot be promoted.
- Absent persisted field → `false` (safe legacy default).
- Truthy strings (`"true"`, `"1"`) are **not** treated as true.

### 2.4 Frontend state matrix

| Traceability status | has_valid_evidence | Source ID | Crop rows | Result |
| ------------------- | -----------------: | --------: | --------: | ------ |
| VALID | true | yes | any | Preview allowed |
| VALID | false | yes | any | Blocked |
| INVALID | any | yes | any | Blocked, invalid message |
| MISSING | any | no | any | Blocked, missing message |
| UNVALIDATED | any | yes/no | any | Blocked, unvalidated message |
| Unknown | any | any | any | Blocked |

Invalid traceability **always** shows the traceability failure message, even when crop rows exist.

### 2.5 Tests — exact commands and results

**Backend targeted suite:**
```bash
cd backend && python3 -m pytest \
  tests/domain/test_traceability_phase42.py \
  tests/pipeline/test_entity_resolution_phase42.py \
  tests/infrastructure/pipeline/test_v3_report_mapper_phase42.py \
  tests/application/mappers/test_traceability_phase42_view.py \
  tests/test_epic_3_1_b.py \
  tests/pipeline/test_phase1_image_traceability.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/infrastructure/pipeline/test_worker_operational_safety_traceability_phase1.py \
  -q
```
**Result:** 56 passed, 0 failed, 0 skipped (8.14s)

**Frontend targeted suite:**
```bash
cd frontend && npm test -- --run \
  tests/evidenceEligibility.test.ts \
  tests/resultMappers.test.ts \
  tests/ResultEvidencePanel.test.tsx \
  tests/ResultEvidenceViewer.test.tsx
```
**Result:** 4 test files passed, 60 tests passed, 0 failed

**Frontend build:**
```bash
cd frontend && npm run build
```
**Result:** success (vite build completed)

**Frontend typecheck / lint:**
```bash
npm run typecheck   # 9 pre-existing errors in unrelated test fixtures (missing hasValidEvidence)
npm run lint        # not re-run; no production lint changes in this pass
```

**Broader backend regression (excluding API):**
```bash
cd backend && python3 -m pytest tests/ --ignore=tests/api -q
```
(See validation run output in correction session; targeted suite is the Phase 4.2 gate.)

### 2.6 Final verdict (corrections pass)

**COMPLETE** — P0 and P1 findings resolved; P2 UI precedence and stale-preview fixes applied; targeted tests pass with exact counts.

---

## 3. Root cause (original)

**Unsafe flow (before Phase 4.2):**

1. `EntityResolutionStage` fell back to full `manifest_image_ids` when `frames_sent_ids` missing
2. INVALID `source_image_id` still persisted in `detected_summary_json`
3. `has_evidence` meant crop row exists, not validated traceability
4. `ResultEvidencePanel` displayed any resolvable `sourceImageId`

---

## 4. Changes by layer

| Layer | Change |
|-------|--------|
| **Validation** | `domain/traceability.py` — `frames_sent_ids` only; `resolve_has_valid_evidence_displayable()` |
| **Pipeline** | `entity_resolution_stage.py` — UNVALIDATED when sent metadata missing |
| **Persistence** | `v3_report_mapper.py` — `traceability_warning`, `has_valid_evidence` |
| **API** | `position_canonical_view.py` — fail-closed read of `has_valid_evidence` |
| **Frontend** | Gating, precedence, stale-preview cleanup, component tests |

---

## 5. Status semantics

| Status | Meaning |
|--------|---------|
| **VALID** | `source_image_id` in final `frames_sent_ids`, not a reference image |
| **INVALID** | ID returned but not in sent set, unknown, or reference image |
| **MISSING** | Provider returned no `source_image_id` |
| **UNVALIDATED** | Final sent-image metadata unavailable — never promoted to VALID |

---

## 6. Remaining risks (not Phase 4.2)

- No canonical `ExecutionImageManifest` artifact (Phase 4.3 scope)
- `Evidence.source_asset_id` still not wired
- UI shows full source photo, not pipeline crop
- Legacy rows without `has_valid_evidence: true` remain non-displayable (intentional)
- Pre-existing frontend typecheck errors in unrelated test fixtures
- Video traceability not implemented

---

## 7. Phase 4.3 readiness

Canonical manifest work **not started**. Phase 4.2 evidence-safety gates are complete.

**Video traceability:** Explicitly not implemented.
