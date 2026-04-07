
# Full implementation audit — multi-provider / multi-run rollout

## 1. Executive summary

**Solid:** Multi-run persistence primitives are largely in place (`positions.job_id`, label/final-count tables, `inventory_jobs` provider/model/prompt + `engine_params_json`, `aisles.operational_job_id`). A real **`ResultContextResolver`** drives list/detail flows with explicit → operational → legacy → **`latest_succeeded`** semantics. **POST process** resolves provider/model/prompt server-side (`resolve_start_processing_request`, `aisles.py`). **Phase 4 executor wiring** is documented and implemented: native **`GeminiSdkAdapter`** / **`OpenAiSdkAdapter`**, transitional bridge only for **`fake`** (`registry.py`, `multi_provider_phase4_closure.md`). **Provider-aware hybrid prompts** and **LLM JSON normalization** (`entity_normalizer.py`) plus **analysis-stage** application exist. **Mapper quantity fix** (`_qty_from_entity` treating `final_quantity: null` vs `product_label_quantity`) addresses OpenAI-style reports reaching persist layer. **Frontend** has run selection (`AisleRunSelector.tsx`), `jobId` query usage (`PositionDetailPage.tsx`), and a **processing dialog** with provider/model/prompt fed by **`GET .../processing-provider-options`** (`InventoryDetail.tsx`, `inventories.py`).

**Partially complete:** Planning revision **DoD items** on analytics (per-aisle operational slice, benchmark exclusion at repository layer), **evidence/preview paths** (no implicit latest job), **prompt traceability** (`prompt_version` / rendered snapshot on **`inventory_jobs`**), and **full shared-services extraction** from vendor code are **not** fully realized. Docs **`multi_provider_audit_final.md`** still describe pre-fix blockers (e.g. mapper without `job_id`) that **contradict current code**.

**Still missing / deferred:** Benchmark analytics, batch “run all”, correction transfer, strict enforcement of “no latest job” everywhere, and end-to-end proof for every evidence/export edge case.

---

## 2. Phase-by-phase status

Aligned to `multi_provider_implementation_plan.md` phases + planning revision.

### Phase 1 — Persistence isolation + legacy compatibility  
**Status: Done (core)**  
**Evidence:** `schema.sql` / `0010_multi_run_job_scoping.sql` — `positions.job_id`, `raw_labels.job_id`, `normalized_labels.job_id`, `final_count_records.job_id`; `inventory_jobs` columns `provider_name`, `model_name`, `prompt_key`, `engine_params_json`; index `IX_positions_aisle_job_id`.  
**Gaps:** Planning revision optional uniqueness `(aisle_id, job_id, position_code)` remains **open** (documented, not enforced in reviewed schema).

### Phase 2 — API job-scoped reads + Result Context Resolver  
**Status: Partially done**  
**Evidence:** `result_context_resolver.py` (explicit / operational / legacy / **`latest_succeeded`**); wired via `dependencies.py`; positions routes (`positions.py`) and list use cases (`list_aisle_positions.py`, tests `test_phase2_list_positions_result_context.py`, `test_result_context_resolver.py`).  
**Gaps:** Resolver’s **`latest_succeeded`** is a **transitional default** (module docstring) — not identical to “operational or legacy only” in the strictest reading of the revision. Merge/export/evidence need spot checks (see §5).

### Phase 3 — Frontend browsing  
**Status: Partially done**  
**Evidence:** `AisleRunSelector.tsx` (operational badge, `?jobId=` copy); `PositionDetailPage.tsx` passes `jobId`; `InventoryDetail.tsx` jobs UI.  
**Gaps:** Full KPI correctness vs backend resolver for every screen not verified here; review drawer editability vs benchmark is **policy** — enforce at API (needs alignment checks per feature).

### Phase 4 — Provider abstraction cleanup  
**Status: Partially done**  
**Evidence:** `LlmGlobalAnalysisExecutor`, `HybridGlobalAnalysisStrategy`, `registry.py`, `multi_provider_phase4_closure.md`. Prompt assembly in `hybrid_analysis_prompt.py` + `provider_keys.py` avoids importing heavy registry from prompt path.  
**Gaps:** Plan’s “shared analysis services” as a **clean layer** is only **partially** met — logic is split across `src/llm/`, `src/pipeline/services/`, `src/infrastructure/pipeline/v3_report_mapper.py` rather than a single “SharedAnalysisServices” module. **`LLMRequest`/`LLMResponse` names** are noted as historical in Phase 4 doc — **mildly misleading** for new readers.

### Phase 5 — New provider + configurable start  
**Status: Partially done**  
**Evidence:** `OpenAiSdkAdapter`, registry key `openai`; `start_aisle_processing` uses `resolve_start_processing_request` (`aisles.py`); `GET .../processing-provider-options` (`inventories.py`); provider-aware `get_hybrid_prompt` (`prompts.py`); normalization (`entity_normalizer.py`, `analysis_stage.py`).  
**Gaps:** OpenAI output/schema drift vs Gemini is **mitigated**, not eliminated (normalizer is incremental). **E2E** OpenAI job → DB → `/positions` less certain than unit/integration coverage.

### Phase 6 — Benchmark UX / refinements  
**Status: Not done (as scoped)** — compare UX, benchmark KPIs, advanced exports: explicitly post-MVP in plans.

---

## 3. Additions beyond the original plan

| Addition | Classification |
|----------|----------------|
| **`latest_succeeded` result context** when legacy empty | **Acceptable transitional** — documented in `result_context_resolver.py`; avoids empty aisles but diverges from strict “only operational or legacy” wording. |
| **`entity_normalizer` + quantity/bbox aliasing** | **Aligned**; **required for correctness** for OpenAI-shaped JSON. |
| **Provider-aware prompt profiles** (`default` / `openai`) | **Aligned** with multi-provider goals. |
| **`provider_keys.py`** to avoid import cycles | **Aligned** (practical hardening). |
| **`_qty_from_entity` fix** (`final_quantity` null vs `product_label_quantity`) | **Aligned**; **required** so normalized quantities persist as explicit. |
| **`label_explicit` qty provenance** | **Aligned** with canonical view (`position_canonical_view.py`). |
| **Analytics module honesty** (`sql_analytics_repository.py` header: not filtered to operational slice) | **Aligned** with transparency; flags **product risk** until fixed. |
| **Phase 4 closure doc** (`multi_provider_phase4_closure.md`) | **Aligned** documentation. |

---

## 4. Missing work

### Critical
- **Operational analytics at repository layer:** `sql_analytics_repository.py` explicitly states aggregates are **not** filtered to `operational_job_id` / resolver semantics — **violates** `multi_provider_planning_revision.md` §4.2 / implementation plan §5.11.
- **Evidence / asset “latest job” elimination:** `shared.py` HEIC preview path logs **fallback to latest job for aisle** — **direct conflict** with revision §4.1 / §6 DoD (“no implicit latest job”).
- **`prompt_version` / rendered prompt on `inventory_jobs`:** Planning revision recommends for comparability; **`Job` dataclass** (`domain/jobs/entities.py`) shows **no** `prompt_version` field — traceability gap vs plan (legacy `jobs` table may have `prompt_version` in schema for worker path — **split-brain** risk between job models).

### Important
- **Static/architectural guard** against new “latest aisle job” queries (revision §7 testing).
- **Full E2E tests:** OpenAI run → persist → positions API → quantity/SKU fields.
- **Doc refresh:** `multi_provider_audit_final.md` persistence matrix / mapper bullets are **stale** vs `v3_report_mapper.py` (`Position.job_id=job_id`, `RawLabel.job_id`).

### Nice to have
- Benchmark analytics, batch sessions, compare export pivot, promotion UX polish.
- Unified “Shared analysis services” package as in plan diagram.

---

## 5. Current inconsistencies

- **Docs vs code:** `multi_provider_audit_final.md` §5 still implies **`map_hybrid_report_to_domain`** does not attach run identity to positions — **false** today (`Position(..., job_id=job_id)` in `v3_report_mapper.py`). User-requested filename **`phase4_provider_executor_closure.md`** does not exist; actual is **`multi_provider_phase4_closure.md`**.
- **Planning revision DoD vs analytics:** Revision requires benchmark exclusion at query layer; **code admits** it does not (`sql_analytics_repository.py`).
- **Resolver philosophy vs `latest_succeeded`:** Revision stresses explicit context; code adds **latest succeeded** fallback — **documented** but **behaviorally** looser than strict reading.
- **UI vs backend:** `AisleRunSelector` explains backend picks **operational / legacy / latest-succeeded** — matches resolver; **dashboard KPIs** may **not** match selected run (analytics scope).
- **Provider architecture vs names:** `LLMRequest`/`LLMResponse` — **historical semantics** per Phase 4 doc; **misleading** for “provider-neutral” narrative.
- **Normalization vs persistence:** Normalizer fixes JSON; **mapper** had separate bug (`final_quantity` null). Both must stay aligned; **consolidated counts** path uses `apply_to_product_records=False` in `persist_aisle_result.py` — **correct** for not overwriting explicit qty but **subtle** for operators expecting merge to change product qty.

---

## 6. Risks

1. **KPI / operational truth divergence** — analytics counting all positions while UI shows one slice → **wrong business decisions**.  
2. **Wrong crop/preview under multi-run** — any **latest-job fallback** (`shared.py`) → **wrong evidence** when multiple runs exist.  
3. **OpenAI / future models** — normalization is **incremental**; new field aliases → **silent loss** until mapper/parser updated.  
4. **Prompt comparability** — without **`prompt_version` or snapshot on the v3 `Job`/`inventory_jobs` path**, benchmarks are **weaker** than revision requires.  
5. **Transitional `latest_succeeded`** — operators may think they see “legacy” when they see **newest job** — **education + UI labeling** risk.

---

## 7. Recommended next implementation targets (priority order)

1. **Align SQL analytics** with per-aisle operational + legacy-null + benchmark exclusion (shared query composition as per revision).  
2. **Audit and remove/replace** evidence/preview/asset fallbacks that use **latest job for aisle**; route through **result context** or explicit `job_id`.  
3. **Close traceability gap:** add **`prompt_version` and/or persisted rendered prompt** to **`inventory_jobs` / `Job`** flow used by v3 processing, or formal written risk acceptance in docs.  
4. **Refresh `multi_provider_audit_final.md`** (and cross-links) so persistence/API sections match code.  
5. **E2E / integration tests:** two jobs same aisle → positions list by `jobId` → export → analytics numbers match slice.  
6. **Optional:** consolidate “shared analysis services” naming/structure per plan §8.5 for onboarding clarity.

---

## 8. Final verdict

**Ready with caveats.**

**Why:** Core **multi-run persistence**, **resolver-driven reads**, **configurable processing**, **OpenAI native executor path**, **prompt + normalization + mapper fixes** are **real in code** and tested in **meaningful** unit/integration areas. The product is **not** fully aligned with the **strictest** planning revision on **analytics scope** and **evidence/latest-job ban**; **documentation drift** on the old audit file **misstates** current mapper behavior. Shipping **without** fixing analytics and evidence fallbacks leaves **known** operational and trust risks called out **explicitly in code comments** (`sql_analytics_repository.py`) and **debug logs** (`shared.py`).