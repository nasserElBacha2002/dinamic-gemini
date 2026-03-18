# Artifact vs DB Boundary — Historical Read and Degradation (3.2.5 Phase 7)

**Release**: 3.2.5 — Phase 7 (Artifacts and Historical-Read Consistency)  
**Purpose**: Define the boundary between DB-backed result truth and filesystem-backed artifacts so that missing artifacts do not corrupt lifecycle or result semantics. This document states what is authoritative, what degrades when artifacts are missing, and how HEIC preview fallback must be interpreted.

---

## 1. Authority: DB vs filesystem

| Concern | Authoritative source | Filesystem role |
|--------|----------------------|-----------------|
| Job existence / ownership / status | DB (`inventory_jobs`, `JobRepository`) | Execution-log events (best-effort) |
| Asset identity (what assets belong to an aisle) | DB (source_assets, API list) | Bytes served from filesystem |
| Position result truth (status, qty, needs_review, review state) | DB (positions, product_records, review_actions) | — |
| Traceability/source-image metadata on position summary | DB when persisted in `detected_summary_json` | Best-effort enrichment from `hybrid_report.json` |

**Rule**: Persisted result semantics (status, qty, corrected_quantity, qtySource, needs_review, review_actions) are **never** altered or invalidated by missing or stale filesystem artifacts.

---

## 2. Hybrid report enrichment is non-authoritative

The fields `source_image_id`, `traceability_status`, and `source_image_original_filename` on the position summary may be **best-effort enriched** from `{output_dir}/{job_id}/run/hybrid_report.json` when:

- The position has an `entity_uid` in its stored summary, and  
- At least one of those three fields is missing from the stored summary.

**Important**:

- This enrichment is **non-authoritative metadata enrichment** for traceability and support (e.g. linking to source image, showing validation status).
- It **must never alter** persisted result semantics (qty, status, needs_review, corrected_quantity, qtySource, or review-related persisted truth).
- Persisted qty/status/review truth remains **DB-authoritative** regardless of whether enrichment is available or not.

---

## 3. Missing `hybrid_report.json` degrades list/detail metadata only

When no matching `{output_dir}/{job_id}/run/hybrid_report.json` exists (or the file is invalid/unreadable):

- **List**: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` still returns **200**.
- **Detail**: `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}` still returns **200**.
- **Result semantics** remain **DB-derived**: status, needs_review, qty, corrected_quantity (when applicable), qtySource, and review-related persisted truth are coherent and authoritative.
- **Only optional enrichment fields** degrade to `null` (or absent): `source_image_id`, `traceability_status`, `source_image_original_filename`.
- List and detail responses remain **semantically aligned** for these fields; missing enrichment does not cause list and detail to diverge.

The API **must not fabricate** non-null values for these enrichment fields when the enrichment artifact is missing; any value for them must come from persisted DB-backed contract input (e.g. stored in `detected_summary_json` at persist time).

---

## 4. HEIC preview fallback is best-effort, not exact-run fidelity

When the client requests a normalized preview with an explicit `job_id` (e.g. for a position tied to a specific run):

- The backend first tries to resolve the normalized asset from that job’s run (manifest + file on disk).
- If that resolution **fails** (e.g. run dir missing, manifest missing, or normalized file missing), the backend may **fall back** to the aisle’s **latest job** to serve a preview.

**Important**:

- This fallback is **best-effort preview behavior** only.
- It is **not exact-run fidelity**: a successful preview response after fallback does **not** prove that the image came from the requested run.
- Operators and debuggers **must not** interpret a successful fallback preview as proof that the artifact belongs to the requested `job_id`; it may be from a different (e.g. latest) job.

---

## 5. Execution-log: meaning of `events: []`

The execution-log endpoint `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log` returns a list of diagnostic events from the filesystem artifact `{output_dir}/{job_id}/run/execution_log.jsonl`.

**Important**:

- **`events: []` is a degraded diagnostic payload.** It does **not necessarily mean** that no pipeline stages executed.
- It may also mean the execution-log artifact is **missing** (run directory or file absent), **invalid** (e.g. unreadable, or all lines malformed), or **unreadable** (I/O error).
- **Job lifecycle truth** (existence, status, ownership) still comes from the **DB/repository**. The route validates job existence and job–aisle–inventory ownership from DB before attempting any filesystem read. Missing or empty log artifacts do not change lifecycle state.
- Execution-log is **diagnostic best-effort only**; the release does not overclaim exact execution-log availability.

---

## 6. Deferred items

- Storage redesign or moving execution-log/hybrid_report into DB.
- Broader observability platform or review UX changes.
- Making list/detail depend more heavily on artifacts (they must remain DB-authoritative with optional enrichment only).

---

## References

- Execution log module: `backend/src/pipeline/execution_log.py` (`read_execution_log`)
- Route: `backend/src/api/routes/v3/aisles.py` (`get_job_execution_log`)
- Execution log / lifecycle: `docs/3.2.5/JOB_LIFECYCLE_3_2_5.md`
- Debugging and observability: `docs/3.2.5/DEBUGGING_AND_OBSERVABILITY.md`
- Shared enrichment: `backend/src/api/routes/v3/shared.py` (`_enrich_position_traceability_from_report`, `position_to_summary`)
