# Multi-Provider Architecture — Planning Revision (Aligned Audit + Plan)

This document revises and aligns `multi_provider_audit_final.md` and `multi_provider_implementation_plan.md` for implementation readiness. It preserves Strategy + Adapter, job-scoped results, operational job promotion, and MVP scope discipline. No implementation is described here beyond engineering rules and DoD.

---

## 1. Executive summary of corrections applied

- **Run identity & traceability**: Split *execution identity* (who/what variant ran), *execution tuning* (`engine_params_json` and similar), and *traceability* (reproducibility over time). Clarified that indexed columns `provider_name`, `model_name`, `prompt_key` remain the primary filterable identity, but **`prompt_key` alone is insufficient** if template bodies change without a version bump. Recommended explicitly adopting **`prompt_version` and/or a persisted rendered-prompt snapshot** (or both) so historical runs stay comparable when templates evolve. **`engine_params_json` is not primary identity** and must not be the only basis for comparing runs.

- **Positions & uniqueness**: Kept **`position_id` globally unique**. Added explicit distinction between **storage isolation** (no physical row collision across jobs via `job_id`) and **logical identity** (`position_code` and similar may repeat across jobs in the same aisle). Documented **open design decision** on optional DB guardrails (e.g. index `(aisle_id, job_id)`, optional uniqueness on `(aisle_id, job_id, position_code)` when the pipeline can support it).

- **Evidence / assets / previews**: Elevated to **critical architectural rule**: no evidence, crop, source preview, or image-display path may resolve data using **“latest job”** or other implicit run heuristics once multi-run exists. Reads must resolve the **selected result context** first, then traverse `position_id` (MVP). Aisle-wide helpers with implicit latest-run assumptions must be **refactored or banned**.

- **Review model**: **MVP** — `review_actions` stay scoped by **`position_id` only**; **no `job_id` on `review_actions` is required**. The editable dataset is constrained by **`operational_job_id`** + position membership. Benchmark jobs **read-only**; **no automatic correction transfer** in MVP. Future transfer/mapping is **optional later**, not a prerequisite for rollout. Audit matrix language updated so **`job_id` on `review_actions` is not mandatory for MVP**.

- **Analytics**: Default operational analytics include **only** (a) positions tied to **`operational_job_id`** per aisle, and (b) **legacy** rows with **`job_id IS NULL`** where the aisle has no promoted job. **Mixed inventories** (some aisles legacy, some operational) apply this **per aisle**. Exclusion of benchmark jobs should be enforced **in repository/query selection**, not only ad hoc in endpoints. **Benchmark analytics** are **out of MVP scope**.

- **“Run all” future**: MVP remains **one request → one job**. Added a **future-compatible** note: parent benchmark session / batch entity, grouping jobs, UI grouping, concurrency and cost controls — **not required for MVP**.

- **Provider abstraction**: **Wrapping Gemini in an interface is insufficient**. Required extraction of shared logic (prompt assembly/rendering, visual reference enrichment, structured output validation, retry-independent tracing/logging, canonical response normalization). **Pipeline core depends only on stable internal contracts**, not vendor request/response shapes.

- **DoD & testing**: Expanded expectations for two-run isolation, explicit `job_id` selection, operational/legacy fallback, evidence/crop/preview per job, export without duplicate rows after benchmarks, mixed legacy/operational analytics, benchmark exclusion from KPIs, review editability rules, provider contract tests, and **no endpoint relying on implicit latest-job behavior**.

---

## 2. Updated architecture decisions

| Decision | Status |
|----------|--------|
| Strategy + Adapter for providers; mapper layer for internal ↔ external shapes | **Unchanged** |
| Job-scoped persistence for position graph and merge-related tables | **Unchanged** |
| Single `operational_job_id` per aisle; benchmark jobs persisted but non-operational by default | **Unchanged** |
| **Result Context Resolver** centralizes explicit `job_id` / operational / legacy resolution | **Unchanged**; now **mandatory** for every read path that could touch run-specific data |
| **Evidence and asset endpoints** must participate in the same result context; **latest-job heuristics forbidden** | **Strengthened** (critical) |
| **Analytics** default scope = operational job + legacy null-job rows only; benchmark excluded at query layer | **Specified** |
| **Run traceability** beyond `prompt_key`: add **`prompt_version` and/or rendered prompt snapshot** | **New recommendation** |
| **`engine_params_json`**: tuning/trace detail, **not** primary run identity | **Clarified** |
| MVP: **no `job_id` on `review_actions`**; no correction transfer | **Explicit** |
| MVP: **no “run all” orchestration**; future batch/session entity documented | **Clarified** |

---

## 3. Updated domain / persistence clarifications

### 3.1 Execution identity vs tuning vs traceability

| Concern | Belongs to | Examples |
|--------|------------|----------|
| **Execution identity** | Stable comparison of “which variant ran” | `provider_name`, `model_name`, `prompt_key`, (recommended) `prompt_version`, job row identity |
| **Execution tuning** | Reproducing behavior approximations; not for stable cross-run identity alone | `engine_params_json`: temperature, max tokens, retries, vendor knobs |
| **Execution traceability** | Audit and long-term benchmarking defensibility | Timestamps, job status, optional **rendered prompt snapshot**, structured logs, links to artifacts |

**Rules:**

- Indexed columns **`provider_name`, `model_name`, `prompt_key`** remain required on `inventory_jobs`.
- **`prompt_key`**: must remain **stable** for a given logical prompt *definition*; if editors change template text without changing key, historical comparability breaks. Mitigation: **`prompt_version`** (monotonic or semver-like) and/or **persisted rendered prompt** at execution time.
- **`engine_params_json`**: must **not** be the only field used to decide “same run family” or to compare runs in analytics; it is **supporting**, not primary identity.

### 3.2 Positions: storage isolation vs semantic identity

- **`position_id`**: **globally unique** (e.g. UUID); unchanged.
- **`job_id`**: ensures **physical row isolation** between runs: two jobs → two sets of rows, no overwrite.
- **`position_code` (or equivalent business key)**: **may repeat across jobs** in the same aisle when the detector emits the same code in a new run. That is **semantic ambiguity across runs**, not a storage collision.
- **Job isolation** prevents row collision; it does **not** automatically deduplicate “the same logical shelf location” across runs.

**Open design decision (explicit):**

- Whether to add **repository/DB guardrails** such as:
  - index on **`(aisle_id, job_id)`** for list/filter performance (recommended where query plans need it);
  - **optional** uniqueness on **`(aisle_id, job_id, position_code)`** *if and only if* the detection pipeline can guarantee stable uniqueness within a run.
- If the pipeline **cannot** guarantee per-run uniqueness of `position_code`, **do not** enforce a strict unique constraint; document the resulting **operational meaning** (multiple rows same code within a job possible).

### 3.3 Indirect job scope (MVP)

- **`product_records`**, **`evidences`**: remain indirectly job-scoped via **`position_id`** in MVP.
- **Critical**: indirect linkage does **not** permit resolving assets by “any position in aisle”; the **position set** must come from the **resolved job context** first.

### 3.4 Merge / labels / final counts

- Unchanged direction: **`job_id`** on `raw_labels`, `normalized_labels`, `final_count_records` to prevent cross-run merge pollution.

---

## 4. Updated API / analytics / review clarifications

### 4.1 API & result context

- All job-aware list/detail/export/merge paths use the **Result Context Resolver** (explicit `job_id` → operational → legacy).
- **Evidence, crops, source previews, image URLs**: must receive or derive context such that they **never** assume “latest successful job” for an aisle. **Verification** is part of DoD (see §7).

### 4.2 Analytics (precise default rule)

**Default operational analytics** must include rows where, **per aisle** (or equivalent grouping in the query):

1. **`job_id` equals that aisle’s `operational_job_id`** when `operational_job_id IS NOT NULL`, **or**
2. **`job_id IS NULL`** when **`operational_job_id IS NULL`** (legacy aisle).

**Exclude** from default operational aggregates:

- All positions (and downstream facts) belonging to **non-operational** jobs for that aisle (benchmark runs).

**Mixed inventory:**

- An inventory may contain **some aisles with `operational_job_id` set** and **some still legacy**. Queries must apply the **per-aisle rule above**, not a single global filter that misclassifies mixed aisles.

**Enforcement layer:**

- Prefer **repository-level or shared query composition** so benchmark rows **cannot** leak into operational KPIs through one forgotten endpoint parameter.

**Benchmark analytics:**

- **Out of MVP scope** (no product requirement to ship benchmark KPIs in the first rollout).

### 4.3 Review (MVP)

- **`review_actions`**: remain keyed by **`position_id`** only; **no `job_id` column required** for MVP.
- **Why this is sufficient**: the only mutable dataset is positions under **`operational_job_id`**; benchmark positions are read-only in product rules; edits cannot target benchmark rows.
- **Review History UI**: must still **filter/display** according to **current result context** so operators do not see corrections from another run’s positions while browsing a benchmark (context is **UI + API position set**, not necessarily a new FK on `review_actions`).
- **Correction transfer / mapping** between runs: **future feature**, explicitly **not** a prerequisite for multi-provider MVP.

### 4.4 Audit document alignment

- The persistence matrix must **not** state that **`job_id` on `review_actions` is mandatory** for MVP. Optional future extension only if product requires cross-run audit linkage without joining through positions.

---

## 5. Updated rollout notes

- Phased rollout in the implementation plan **remains** (persistence → API resolver → frontend → provider cleanup → new provider).
- **Phase 1–2** must treat **evidence/asset paths** as **first-class** alongside positions/merge/export (same resolver discipline).
- **Analytics work** should land with **shared filtering** early enough that **benchmark runs cannot inflate KPIs** after multiple runs on the same aisle.
- **Provider Phase 4**: success criteria include **extracted shared services** (not only a `GeminiProvider` implementing a thin interface).

### 5.1 Future: “run all” / batch benchmarking (not MVP)

- **MVP**: one HTTP/action → **one `inventory_jobs` row**.
- **Future extension** (design placeholder only):
  - **Parent entity**: e.g. `benchmark_session` / `benchmark_batch` grouping **N** jobs created together.
  - **Orchestration**: single user action enqueues **N** jobs with shared metadata (inventory, aisle subset, matrix of provider/model/prompt).
  - **UI**: group display (“Batch from 2026-04-06 10:00”), progress per child job.
  - **Concurrency / cost**: rate limits, max parallel runs, cancellation semantics — **to be defined when the feature is scheduled**.

---

## 6. Updated Definition of Done

### Persistence & identity

- [ ] `inventory_jobs` has indexed **`provider_name`, `model_name`, `prompt_key`**; **`engine_params_json`** present for tuning; **primary run identity** documented as **not** relying solely on JSON parsing.
- [ ] **Prompt traceability**: **`prompt_version` and/or persisted rendered prompt snapshot** implemented **or** explicitly deferred with written risk acceptance (preferred: implement at least one before broad benchmarking in prod).
- [ ] New positions/labels/final counts carry **`job_id`**; legacy **`NULL`** preserved.
- [ ] **`position_id`** globally unique; **`(aisle_id, job_id)`** indexing strategy applied where needed; **uniqueness of `(aisle_id, job_id, position_code)`** decided and documented (constraint or explicit non-guarantee).

### Result context & evidence (critical)

- [ ] **No** evidence, crop, preview, or image endpoint resolves assets using **implicit latest job** for an aisle.
- [ ] Every such path uses **resolved job context** (explicit, operational, or legacy) before loading position-bound artifacts.
- [ ] Aisle-wide helpers that assumed a single run are **removed or rewritten** to accept context.

### API

- [ ] Resolver covers list/detail/export/merge/analytics inputs consistently.
- [ ] **POST /process**: one request → one job (MVP).

### Analytics

- [ ] Default operational analytics follow **per-aisle** operational vs legacy rule; **benchmark jobs excluded** at **query/repository** layer.
- [ ] Mixed inventory behaves correctly.

### Review

- [ ] Edits only on **operational** job positions; benchmark **read-only** enforced.
- [ ] **`review_actions`** without **`job_id`** in MVP is **accepted design**; no spurious schema expansion unless product changes.

### Provider architecture

- [ ] Shared logic **extracted** from vendor code: prompt assembly/rendering, visual reference enrichment, structured output validation, tracing/logging independent of vendor retries, canonical normalization.
- [ ] Core pipeline **imports no vendor-specific types** in generic flows.

### Export

- [ ] Operational export: no duplicate rows from multiple benchmark runs on the same aisle.

---

## 7. Updated testing strategy

### Isolation & selection

- [ ] **Two runs**, same aisle: **no row collision**; distinct `position_id` sets per `job_id`.
- [ ] Read with **explicit `job_id`** returns only that run’s data.
- [ ] **Omit `job_id`**, operational set: uses **`operational_job_id`**.
- [ ] **Omit `job_id`**, legacy aisle: uses **`job_id IS NULL`**.

### Evidence & assets

- [ ] **Preview / crop / source image** for run A **unchanged** when run B exists and is “newer”.
- [ ] **No cross-leakage** between benchmark and operational rendering when switching selected job in UI.

### Export

- [ ] After **multiple benchmark runs**, operational export **excludes** benchmark rows (no duplicated SKUs/lines from extra runs).

### Analytics

- [ ] **Mixed inventory**: legacy aisles + promoted aisles → KPIs match **per-aisle** rules.
- [ ] **Benchmark exclusion**: operational KPIs **unchanged** by adding benchmark jobs (no inflation).

### Review & permissions

- [ ] **Review editability** only operational job; benchmark attempts **rejected** at API or domain layer.

### Provider & architecture

- [ ] **Provider contract tests**: each implementation satisfies internal `AnalysisRequest` / `AnalysisResult` (or equivalent) without exposing vendor shapes to core tests.
- [ ] **Static/architectural check** (manual or lint): **no new** “latest job for aisle” queries in evidence or position flows without resolver.

### Regression

- [ ] Legacy aisles: behavior unchanged for operators until promotion.

---

## 8. Open decisions intentionally deferred beyond MVP

| Topic | Deferred rationale |
|-------|-------------------|
| **Benchmark analytics / KPIs** | Product scope; operational analytics must be correct first. |
| **Automatic correction transfer** between runs (mapping by `position_code`, geometry, etc.) | Complex, audit-heavy; not required for isolation MVP. |
| **`job_id` on `review_actions`** | Optional if future cross-run audit reports need direct FK; MVP sufficient via `position_id` + operational constraint. |
| **Strict `(aisle_id, job_id, position_code)` uniqueness** | Depends on detector guarantees; may remain **non-unique** by design. |
| **“Run all” / batch benchmark sessions** | Orchestration, UI grouping, cost controls — future phase. |
| **Comparative pivot export** | Already noted as post-MVP in plan. |
| **Aggressive backfill** of historical `job_id`** | Explicitly rejected for MVP; nullable columns and forward-only assignment. |

---

## Source documents

- `docs/multi_provider_audit_final.md` — updated to align review_actions MVP stance with this revision.
- `docs/multi_provider_implementation_plan.md` — updated with expanded sections mirroring the rules above (Spanish + cross-reference to this English revision where useful).
