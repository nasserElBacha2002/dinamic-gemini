---
name: cv-inventory-repo-assistant
description: Guides implementation and maintenance of the video inventory (depot/retail) project. Covers pipeline architecture (detection → tracking → identification → consolidation → reports), sprint planning, user stories, code review, and repo conventions. Use when the user mentions sprints, plan, roadmap, user stories, requirements, pipeline, detection, tracking, identification, consolidation, reports, performance, optimization, auditability, logs, outputs, or when editing files under src/ related to the main flow.
---

# CV Inventory Repo Assistant

## Purpose and scope

- **Do:** Implement and maintain the video inventory project with consistent, reviewable code. Respect pipeline architecture, generate sprint plans and user stories when asked, perform code review, maintain outputs/config/logging and modular structure.
- **Do not:** Invent datasets, change stack, or perform large refactors without explicit request.

## Pipeline architecture

The processing unit is **pallet_track** (not frame). Flow:

1. Video → frame extraction
2. Detection (pallets per frame)
3. Tracking (stable `pallet_track_id`)
4. ROI cropping + view selection (3–5 views per track)
5. LLM (Gemini): one request per track, multi-view
6. Post-LLM validation (segregation + determinism)
7. Export: `final_result.json` (OK) + `errors.json` (ERROR)

**Invariants:** One product per pallet (no mixed SKUs → `ERROR: MIXED_SKUS`). If evidence is insufficient for exact count → `ERROR: INSUFFICIENT_EVIDENCE` (never guess).

Module boundaries to respect: detector / tracker / identifier (LLM) / consolidation / reporting (io). Keep separation; avoid hardcoded thresholds—prefer `src/config.py` or env/config files.

For full module map and data contracts, see [reference.md](reference.md).

## Planning output format

When generating **sprint plans**, **user stories**, or **technical tasks**, use Markdown with:

- **Objetivo** / **Alcance** / **Supuestos**
- **Tareas** (ordered, actionable)
- **Criterios de aceptación**
- **Riesgos** (optional)

Keep tasks small and iterative; no “big bang” scope.

## Code review format

When reviewing code under `src/`:

1. **Checklist** (concise): correctness, edge cases, config-driven behavior, determinism/traceability, logging.
2. **Per-file suggestions:** list file path and concrete change (e.g. “move magic number to config”).
3. Severity: Critical (must fix) / Suggestion / Nice-to-have.

Prefer: determinism and traceability (use `UNKNOWN` or explicit errors when evidence is insufficient), configurable thresholds, small incremental changes.

## Outputs and contracts

- **Outputs:** Describe schemas (JSON/CSV) clearly and in a versionable way (e.g. in `src/models/schemas.py` or a dedicated contracts doc). Main exports: `final_result.json`, `errors.json`.
- **Config:** All tunables via `Settings` (config.py) or YAML/TOML/JSON; no hardcoding.

## Conventions

| Rule | Example |
|------|--------|
| Config-driven | `Settings.resize_max_side`, env vars; no literals for thresholds. |
| Determinism | Insufficient evidence → `UNKNOWN` or `ERROR: INSUFFICIENT_EVIDENCE`. |
| Modularity | Do not mix detector/tracker/identifier/consolidation responsibilities in one module. |
| Iterative changes | Prefer small PRs; avoid large refactors unless requested. |
| Stack | Python, CLI, configs (yaml/toml/json). Add dependencies only when clearly needed. |

## Quick reference

- **Planning:** Markdown with Objetivo, Alcance, Supuestos, Tareas, Criterios de aceptación, Riesgos.
- **Review:** Checklist + per-file suggestions; Critical / Suggestion / Nice-to-have.
- **Outputs:** Clear, versioned schema; `final_result.json` + `errors.json`.
- **Code:** Python + config; modular; deterministic; no big refactors unrequested.
