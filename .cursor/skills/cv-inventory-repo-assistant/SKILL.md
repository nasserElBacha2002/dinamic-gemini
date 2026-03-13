---
name: cv-inventory-repo-assistant
description: Guides implementation and maintenance of the Dinamic Inventory product — a v3 operational platform (inventories, aisles, jobs, API, persistence, frontend) with an integrated computer vision processing subsystem. Covers backend clean architecture, v3 API contracts, frontend (React + TypeScript + MUI), full-stack epics, and the CV pipeline (detection → tracking → identification → consolidation → reporting). Use when the user mentions sprints, plan, roadmap, user stories, requirements, API, frontend, inventories, aisles, jobs, pipeline, detection, tracking, identification, consolidation, reports, performance, optimization, auditability, or when editing files under src/ or frontend/src/.
---

# Dinamic Inventory — Repo Assistant

## Purpose and scope

- **Do:** Implement and maintain the product with consistent, reviewable code. Support both the **operational platform** (API, use cases, persistence, frontend) and the **CV processing subsystem** (pipeline, detection, tracking, identification, reporting). Respect clean architecture, generate sprint plans and user stories when asked, perform code review, maintain clear contracts and modular structure.
- **Do not:** Invent datasets, change stack, or perform large refactors without explicit request.

## Product = two connected parts

### 1. Operational inventory platform (v3)

- **Backend:** Clean layers — `api` (routes, schemas, dependencies) → `application` (use cases, ports) → `domain` (entities) → `infrastructure` (repositories, queue, storage). No business logic in routes; use cases depend only on ports.
- **Domain entities:** Inventory, Aisle, Job (v3), SourceAsset, Position, ProductRecord, Evidence, ReviewAction. Status enums and transitions are explicit.
- **API:** v3 endpoints under `/api/v3/` — inventories, aisles, process, status. Thin routes: parse → call use case → serialize. Errors mapped to HTTP (404, 409, 422).
- **Persistence:** SQL (inventories, aisles, inventory_jobs) with repository implementations; optional in-memory fallback. Schema and migrations in `src/database/`.
- **Jobs:** v3 job flow for aisle processing (create job, enqueue, persist, status). Legacy job system (`src/jobs/`, legacy `jobs` table) remains for existing pipeline; v3 uses `inventory_jobs` and application ports.
- **Frontend:** React + TypeScript + Material UI in `frontend/`. Centralized API client, typed DTOs, pages (list, detail), dialogs (create inventory, create aisle). Loading/error states and contract alignment with backend.

### 2. Computer vision / processing subsystem

- **Pipeline unit:** pallet_track (not frame). Flow: video → frames → detection → tracking (stable pallet_track_id) → ROI + view selection → LLM (e.g. Gemini) per track → validation → export (final_result.json, errors.json).
- **Invariants:** One product per pallet (no mixed SKUs → ERROR). If evidence insufficient → UNKNOWN or ERROR: INSUFFICIENT_EVIDENCE (never guess).
- **Module boundaries:** detector / tracker / identifier (LLM) / consolidation / reporting. Keep separation; config-driven thresholds (`src/config.py` or env).

For module map and contracts, see [reference.md](reference.md).

## Planning output format

When generating **sprint plans**, **user stories**, or **technical tasks**, use Markdown with:

- **Objetivo** / **Alcance** / **Supuestos**
- **Tareas** (ordered, actionable)
- **Criterios de aceptación**
- **Riesgos** (optional)

Keep tasks small and iterative. For full-stack epics, call out backend vs frontend vs pipeline work explicitly.

## Code review format

When reviewing code under `src/` or `frontend/src/`:

1. **Checklist (concise):** correctness, edge cases, architecture (layers, routes vs use cases), API/contract alignment, config-driven behavior where relevant, determinism/traceability for processing, logging.
2. **Per-file suggestions:** file path and concrete change (e.g. “move magic number to config”, “route should not call repository directly”).
3. **Severity:** Critical (must fix) / Suggestion / Nice-to-have.

Prefer: determinism and traceability in processing (UNKNOWN when evidence insufficient), configurable thresholds, thin routes and use-case-driven backend, typed frontend and aligned contracts, small incremental changes.

## Outputs and contracts

- **Platform:** API request/response schemas in `src/api/schemas/`; frontend types in `frontend/src/api/types.ts` aligned with backend. Domain entities in `src/domain/`.
- **CV pipeline:** Output schemas (e.g. `src/models/schemas.py`); main exports: `final_result.json`, `errors.json`. Config via Settings (config.py) or YAML/TOML/JSON; no hardcoding.

## Conventions

| Rule | Example |
|------|--------|
| Config-driven | Thresholds and limits in Settings or env; no literals for tunables. |
| Determinism (processing) | Insufficient evidence → UNKNOWN or ERROR: INSUFFICIENT_EVIDENCE. |
| Backend layers | Routes → use cases → ports; no SQL or infra in application/domain. |
| Frontend contracts | Types match backend responses; handle loading/error/empty. |
| Modularity | Do not mix pipeline stages or mix route logic with use cases. |
| Iterative changes | Small PRs; avoid large refactors unless requested. |

## Quick reference

- **Planning:** Markdown with Objetivo, Alcance, Supuestos, Tareas, Criterios de aceptación, Riesgos. For full-stack: call out API, frontend, pipeline.
- **Review:** Checklist + per-file suggestions; Critical / Suggestion / Nice-to-have; apply to both platform and pipeline code.
- **Platform:** api → application → domain → infrastructure; v3 API and frontend aligned.
- **Pipeline:** detection → tracking → identification → consolidation → reporting; config-driven; deterministic outputs.
