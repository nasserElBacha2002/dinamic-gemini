# Epic 5 — Frontend implementation (source_image_original_filename)

**Scope:** Frontend-only. Consume backend field `source_image_original_filename` and surface it in review/result views. Backend already exposes the field in entities API, report, and CSV.

**Source of truth:** Backend EntityListItem / JobEntityListItem include `source_image_original_filename?: string | null`. Only guaranteed for reports generated after Epic 5 (photos jobs); legacy and video jobs return null.

---

## Implemented

### 1. Frontend types (`frontend/src/api/types/responses.ts`)

- **JobEntityListItem:** added `source_image_original_filename?: string | null` (Epic 5: original filename, human-readable).
- **PositionSummary:** added `source_image_original_filename?: string | null` (optional; may be absent until the v3 position API is extended to expose it).

### 2. JobEntitiesPage

- Column **Source image** renamed to **Source image ID** (internal traceability id).
- New column **Source file** shows `source_image_original_filename`; `displayOptional` → "—" when absent.
- Table: Item | Review label | Pallet | Type | Count status | Source image ID | Source file | Traceability.

### 3. PositionDetailPage

- **PositionSummaryCard:** "Source image" → **Source image ID:** `{source_image_id}`; added **Source file:** `{source_image_original_filename}`. Both use "—" when absent.

### 4. Tests

- **JobEntitiesPage.test.tsx:** entity list test includes `source_image_original_filename`; new tests: Epic 5 shows Source image ID and Source file columns and original filename when present; Source file shows — when absent (legacy).
- **PositionDetailPage.test.tsx:** existing tests updated to "Source image ID"; new tests: Epic 5 Source file when present; Source file — when absent.

---

## Semantic distinction

- **Source image ID:** internal traceability identifier (e.g. `img_001`).
- **Source file:** human-readable original filename (e.g. `IMG_1024.JPG`). Only when backend provides it (Epic 5+ photos jobs).

---

## Legacy / safe behavior

- Field optional everywhere; `displayOptional` and null-coalescing yield "—" when absent, null, or empty.
- No crash when backend omits the field or job is video/legacy.

---

## Out of scope (not implemented)

- Backend changes.
- Evidence browser or advanced media UX.
- Other pages beyond JobEntitiesPage and PositionDetailPage (add only where it improves review).
