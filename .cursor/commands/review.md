# review

You are a senior software architect reviewing a production-ready computer vision inventory system.

Run an exhaustive code review of this repository.

How to proceed:
1) First, scan the repo structure and identify the main entrypoints (CLI, pipeline runner, src/ modules).
2) Map the pipeline flow end-to-end (detection → tracking → identification → consolidation → reporting).
3) Review the codebase focusing on production risks, correctness, determinism, and scalability.
4) For every issue, include: severity (CRITICAL/HIGH/MED/LOW), file path(s), and a concrete fix suggestion.
5) Prefer minimal, incremental changes. Do NOT rewrite the project.

Review dimensions (must cover all):
A. Architecture & boundaries
- Module responsibilities and coupling
- Clear interfaces between pipeline stages
- Avoid hidden dependencies and implicit globals

B. Correctness & edge cases
- Failure modes (missing frames, empty detections, tracker drift, duplicates)
- Handling UNKNOWN / ambiguous cases
- Off-by-one, indexing, frame ranges, coordinate transforms

C. Determinism & auditability
- Config-driven thresholds (no hardcoded magic numbers)
- Reproducible decisions
- Traceable outputs (track_id → evidence → final decision)
- Logging quality and event consistency

D. Performance & resource use
- Avoid repeated model initialization
- Batch inference opportunities
- Caching (embeddings, hashes, per-track computed features)
- I/O hotspots (writing crops/frames by default)
- Memory spikes on long videos

E. Scalability & maintainability
- Works with longer videos, bigger SKU catalogs, multiple runs
- Extension points for new detectors/identifiers
- Clear configuration system
- Error handling strategy (fail-fast vs best-effort)
- Code readability and type safety

F. Testing & CI readiness
- Missing unit/integration tests
- Where tests should be added first
- Suggested minimal test plan for the pipeline

G. Security & safety (basic)
- Path traversal / unsafe file writes
- Handling untrusted inputs
- Sensitive data in logs
- Dependency risks (if visible)

Output format (strict):
# Deep Repo Review

## 0) Repo Map
- Entrypoints
- Key modules
- Data / outputs layout

## 1) Pipeline Trace (as implemented)
Bullet list from video input to final outputs, referencing actual modules/files.

## 2) Findings
### CRITICAL
- [Issue] (file:line if possible) → [Why it matters] → [Fix]

### HIGH
...

### MED
...

### LOW
...

## 3) Top 10 Fix Plan (ordered)
A prioritized list of changes that gives the biggest production reliability gain first.

## 4) Quick Wins (≤ 1 day)
Small changes with high ROI.

## 5) Suggested Test Plan
Minimal tests to add next, by module.

Important constraints:
- Keep recommendations realistic for this repo stage.
- Do not invent files that don't exist; reference only what you can find.
- Do not propose big refactors unless necessary for correctness.with /review
