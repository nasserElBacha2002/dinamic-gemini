# review

You are a senior software architect reviewing a production-ready system that includes an **operational platform** (v3 API, use cases, persistence, frontend) and a **computer vision pipeline**.

**Task:** Run an exhaustive code review of this repository.

**How to proceed:**  
1. Scan the repo structure and identify:
   - **Platform entrypoints:** API routes (`src/api/`), dependency wiring, frontend app (`frontend/src/`).  
   - **Application layer:** use cases, ports, domain entities.  
   - **Pipeline:** entrypoints (e.g. hybrid_inventory_pipeline), stages (detection → tracking → identification → consolidation → reporting).  
2. Map **platform flow:** API request → route → use case → ports → infrastructure (repos, queue). Frontend: pages → API client → backend.  
3. Map **pipeline flow** (if present): video input → decode → detection → tracking → … → reporting outputs.  
4. Review the codebase for production risks, correctness, determinism, and scalability in **both** platform and pipeline.  
5. For every issue: severity (CRITICAL / HIGH / MED / LOW), file path(s), and a concrete fix suggestion.  
6. Prefer minimal, incremental changes. Do **not** rewrite the project.

**Review dimensions (must cover all that apply):**

**A. Architecture & boundaries**  
- **Platform:** Module responsibilities; api → use cases → ports → infrastructure; no business logic in routes; clear API contracts and frontend alignment.  
- **Pipeline:** Clear interfaces between stages; no hidden dependencies or implicit globals.

**B. Correctness & edge cases**  
- **Platform:** Validation in use cases; 404/409/422 handling; frontend loading/error/empty states; type safety.  
- **Pipeline:** Failure modes (missing frames, empty detections, tracker drift, duplicates); UNKNOWN / ambiguous cases; off-by-one, indexing, coordinate transforms.

**C. Determinism & auditability**  
- Config-driven thresholds (no hardcoded magic numbers).  
- Reproducible decisions.  
- Traceable outputs (e.g. job/aisle status; or track_id → evidence → decision).  
- Logging quality and event consistency.

**D. Performance & resource use**  
- **Platform:** API/DB N+1, frontend bundle and re-renders.  
- **Pipeline:** Repeated model init, batching, caching, I/O hotspots, memory on long videos.

**E. Scalability & maintainability**  
- Longer runs, more data, multiple clients.  
- Extension points (new use cases, new pipeline stages).  
- Clear configuration; error-handling strategy; readability and type safety.

**F. Testing & CI readiness**  
- Missing unit/integration tests (use cases, API, repos, frontend, pipeline).  
- Where to add tests first.  
- Minimal test plan for platform and/or pipeline.

**G. Security & safety (basic)**  
- Path traversal / unsafe file writes.  
- Untrusted inputs (API, uploads).  
- Sensitive data in logs.  
- Dependency risks if visible.

**Output format (strict):**

# Deep Repo Review

## 0) Repo Map  
- Platform: entrypoints, key modules, data/API layout, frontend structure.  
- Pipeline (if present): entrypoints, stages, outputs.

## 1) Platform Trace (as implemented)  
Bullet list from API request to response and frontend to backend, referencing actual modules/files.

## 2) Pipeline Trace (as implemented, if present)  
Bullet list from video input to final outputs, referencing actual modules/files.

## 3) Findings  
### CRITICAL  
- [Issue] (file:line if possible) → [Why it matters] → [Fix]  
### HIGH / MED / LOW  
- ...

## 4) Top 10 Fix Plan (ordered)  
Prioritized list for biggest production reliability gain.

## 5) Quick Wins (≤ 1 day)  
Small changes with high ROI.

## 6) Suggested Test Plan  
Minimal tests to add next, by module/layer.

**Constraints:**  
- Keep recommendations realistic for this repo stage.  
- Do not invent files; reference only what you can find.  
- Do not propose big refactors unless necessary for correctness.

This command will be available in chat with /review
