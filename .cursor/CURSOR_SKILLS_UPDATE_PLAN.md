# Cursor Skills/Commands Update Plan

## 1. Current commands/skills inventory

| Name | Purpose | Current usefulness | Status |
|------|---------|--------------------|--------|
| **cv-inventory-repo-assistant** (SKILL.md) | Main repo skill: pipeline architecture, planning, code review, conventions | Partially valid; describes only CV pipeline (detection→tracking→identification→consolidation→reports). Does not mention v3 platform, API, frontend, inventories/aisles/jobs. | **REWRITE** |
| **cv-inventory-repo-assistant/reference.md** | Pipeline modules and data contracts reference | Valid for CV subsystem only; no v3 API/domain/use_cases. | **UPDATE** |
| **code-reviewer** (agent) | Structured code review for changes under src/ | Good structure; assumes only pipeline (detection→…→reporting). Must also cover API, use cases, frontend, contracts. | **UPDATE** |
| **bug-investigate** | Systematic debug plan + hypotheses for CV pipeline bugs | Strong format; pipeline stages are decode/detection/tracking/identification/consolidation/reporting only. Must add API, persistence, jobs, frontend. | **UPDATE** |
| **corrections** | Corrective refactor with strict scope; lists specific fixes (bbox, dedupe, evidence_index, jobs result mode, config) | Too specific to a one-off fix list (bbox parsing, set-based dedupe, evidence_index path, etc.). Not reusable. | **ARCHIVE** (or REWRITE as generic “scope-controlled corrections”) |
| **implement** | Implement feature from plan; workflow: read plan → inspect repo → implementation plan → implement → validate | Good workflow; assumes “pipeline entrypoint(s)”, “reporting/API contracts”. Should explicitly include API routes, use cases, frontend, DB. | **UPDATE** |
| **perf-audit** | Performance audit: runtime flow, model lifecycle, I/O, caching, memory, concurrency | Pipeline-centric (decode, detection, tracking, cropping, identification, reporting). Should add API/DB/frontend hot paths. | **UPDATE** |
| **plan-featured** | Feature plan: scope, pipeline placement, design, tasks, acceptance criteria | “Pipeline placement” assumes detection→…→reporting only. Should support platform features (API, UI, jobs) and CV features. | **UPDATE** |
| **prod-readiness** | Production readiness: reliability, determinism, observability, contracts, performance, security, deployment, testing | Good dimensions; no mention of API, frontend, or full-stack. | **UPDATE** |
| **review-branch** | Review branch vs main: changed files, correctness, architecture, determinism | Focus on src/ and “pipeline-related modules”; asks “detection→…→reporting separation?”. Must add API, frontend, use cases, contracts. | **UPDATE** |
| **review** | Deep repo review: pipeline trace, findings, top fixes, test plan | Entirely pipeline-focused (detection→tracking→…→reporting). Must add platform map (API, domain, frontend) and both platform + pipeline findings. | **UPDATE** |

---

## 2. Main gaps vs current product state

- **Product is two-part:** (1) **Operational platform**: inventories, aisles, jobs, v3 API, SQL persistence, React frontend, full-stack epics. (2) **CV processing subsystem**: detection, tracking, identification, validation, reporting, pipeline/job execution. Current skills/commands describe only (2) or assume a single “video pipeline” codebase.
- **Backend architecture is under-described:** Clean layers (api → application/use_cases → ports → infrastructure), domain entities, repositories, use cases, dependency injection. No command tells the model to consider routes vs use cases vs repositories.
- **Frontend is invisible:** React + TypeScript + MUI, pages/dialogs, API client, types. Review/plan/bug commands do not mention frontend or E2E contracts.
- **API contracts:** v3 endpoints (/api/v3/inventories, aisles, process, status), request/response schemas, error semantics (404, 409, 422). Not referenced in commands.
- **Jobs flow:** Aisle processing, job queue, job status, v3_jobs. Only “jobs” in legacy sense (pipeline job dirs) appears today.
- **Full-stack epics:** Work spans backend + frontend + processing. Plan/implement/review should support “platform + pipeline” scope explicitly.

---

## 3. Proposed new skill/command architecture

| Category | Items | Role |
|----------|--------|------|
| **Full-stack / product** | Main skill (cv-inventory-repo-assistant), reference.md | Single source of truth: product = platform + CV subsystem; backend layers; frontend; API; when to use which. |
| **Implementation** | implement, plan-featured | Support both platform work (API, use cases, DB, frontend) and CV work (pipeline, detection, tracking, etc.); same discipline (incremental, config-driven, tests). |
| **Review** | review, review-branch, code-reviewer | Cover API, use cases, persistence, frontend, and pipeline; severity + minimal fixes; no large rewrites. |
| **Debugging / investigation** | bug-investigate | Classify by area (API, persistence, use cases, frontend, pipeline stage); same structured hypotheses + evidence. |
| **Production / performance** | prod-readiness, perf-audit | Add API/DB/frontend to dimensions; keep CV pipeline; keep severity and actionable recommendations. |
| **Archived** | corrections | Remove or replace with generic “scope-controlled corrections” command (no one-off fix list). |

---

## 4. Files to modify

- `.cursor/skills/cv-inventory-repo-assistant/SKILL.md`
- `.cursor/skills/cv-inventory-repo-assistant/reference.md`
- `.cursor/agents/code-reviewer.md`
- `.cursor/commands/bug-investigate.md`
- `.cursor/commands/implement.md`
- `.cursor/commands/perf-audit.md`
- `.cursor/commands/plan-featured.md`
- `.cursor/commands/prod-readiness.md`
- `.cursor/commands/review-branch.md`
- `.cursor/commands/review.md`

---

## 5. Files to create

- Optional: can archive corrections and skip this.

---

## 6. Files to archive/remove

- `.cursor/commands/corrections.md` — **Removed.** Original preserved in `.cursor/archive/corrections-ARCHIVED.md`. Replaced by `corrections-scoped.md`.

---

## 7. Updated command/skill contents

- **Archive:** `.cursor/archive/corrections-ARCHIVED.md` (note + pointer to corrections-scoped)

---

## 8. Migration notes

**What changed**

- **Main skill:** Describes the product as a **v3 inventory operations platform with a CV processing subsystem**. Explicitly includes: backend clean architecture (domain, application, api, infrastructure), inventories/aisles/jobs, v3 API, SQL persistence, frontend (React + TypeScript + MUI), and full-stack epics. Pipeline (detection → tracking → identification → consolidation → reporting) is one subsystem; references reference.md for both platform and pipeline.
- **Reference:** Split into “Platform (v3)” and “CV pipeline”; added API, domain, use cases, repos, frontend; kept pipeline modules and contracts.
- **Commands:** All updated to support **two problem spaces**: (1) operational platform (API, use cases, persistence, jobs, frontend), (2) CV pipeline (detection, tracking, identification, etc.). Same rigor: incremental changes, config-driven, determinism/auditability where relevant, minimal refactors.
- **code-reviewer:** Reviews can target `src/` (backend + pipeline) and `frontend/src/`; checks architecture (layers, routes vs use cases), API contracts, frontend patterns, and pipeline boundaries.
- **corrections:** Old command removed from active use (archived). Optional new command `corrections-scoped` is generic (no hardcoded fix list).

**Old assumptions removed**

- Repo is only a “video inventory pipeline” or “computer vision pipeline”.
- Only pipeline stages (detection → … → reporting) matter for review/plan/bug/audit.
- No frontend, no v3 API, no use cases, no inventories/aisles/jobs.
- “Pipeline entrypoint” is the only integration point; no API or UI.

**How to use the new commands/skills**

- **Main skill:** Invoked when discussing sprints, plan, roadmap, user stories, requirements, **or** pipeline, detection, tracking, **or** API, frontend, inventories, aisles, jobs, full-stack. It sets the mental model: platform + CV subsystem.
- **implement / plan-featured:** Use for any feature: specify whether it’s platform (API/UI/use case/DB) or pipeline (detection/tracking/…) or both; the command will consider the right layers and contracts.
- **review / review-branch / code-reviewer:** Use for any change under `src/` or `frontend/src/`; they will check both platform consistency and pipeline consistency as applicable.
- **bug-investigate:** Describe the symptom; the command will consider API, persistence, use cases, frontend, and pipeline stages and propose hypotheses in the right area(s).
- **prod-readiness / perf-audit:** Run on the whole repo; they will report on API, DB, frontend, and CV pipeline where relevant.

---

*End of plan. Rewritten file contents follow in the next section.*
