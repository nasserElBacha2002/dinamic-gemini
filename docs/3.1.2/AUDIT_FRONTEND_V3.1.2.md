# AUDIT_FRONTEND_V3.1.2.md

## 1. Summary

This document reports the frontend structure audit for Dinamic Inventory v3.1.2. It inventories pages, features, components, hooks, API client, types, and classifies active vs legacy areas and structural issues.

## 2. Scope

- **Included:** `frontend/src/` (App, pages, features, components, hooks, api, utils).
- **Excluded:** Build config (Vite, etc.), static assets; no code changes were applied.

## 3. Findings

### 3.1 Top-level structure

- **api/** — client (`client.ts`), types (`types/`), `queryKeys.ts`. Single API client module.
- **pages/** — `InventoriesList.tsx`, `InventoryDetail.tsx`, `AislePositionsPage.tsx`, `PositionDetailPage.tsx`. Four main pages.
- **features/** — `results/` (results table, detail, filters, mappers, selectors, hooks). One feature module.
- **components/** — UI primitives (`ui/`), dialogs (CreateInventory, CreateAisle), ExecutionLogPanel, etc.
- **hooks/** — `useInventories.ts`, `useAisles.ts`, `usePositions.ts`, `useMutations.ts`; re-exported from `hooks/index.ts`.
- **utils/** — apiErrors, positionStatus, aisleStatus, jobStatus, formatDate, traceability, resultRoutes, etc.

### 3.2 Active product flows

- **Inventories list** → Create inventory → **Inventory detail** (aisles list, create aisle, metrics) → **Aisle positions** (results table, filters, KPIs) → **Position detail** (result detail, evidence, review actions, execution log). All use v3 API from `client.ts`.
- **getJobEntities** (v1) is called from frontend (client + types); usage location: **Unclear** (likely one of the result/entity views or a legacy screen). Requires grep to confirm.

### 3.3 API client and service layer

- **Single client:** `frontend/src/api/client.ts` — all v3 endpoints plus `getJobEntities` (v1). No duplicate client files.
- **Pattern:** Direct `fetch` + `handleResponse`; no separate axios/sdk. Query keys in `api/queryKeys.ts` for React Query.
- **Inconsistency:** One v1 endpoint (`/api/v1/inventory/jobs/{id}/entities`) alongside v3; rest is v3. Acceptable if v1 is still required; otherwise candidate to remove once backend removes it.

### 3.4 Types and models

- **api/types/** — `responses.ts`, `requests.ts`, `shared.ts`, `errors.ts`, `index.ts`. Aligned with backend DTOs (Inventory, Aisle, PositionSummary, PositionDetailResponse, etc.).
- **features/results/types.ts** — ResultSummary, ResultDetail, etc., for UI; mappers convert API position to result.
- **components/ui/types.ts** — Local UI types.
- No duplicate type definitions for the same API contract; results layer adds UI-oriented types that extend or map from API types.

### 3.5 Hooks and shared components

- **hooks:** useInventories, useAisles, usePositions, useMutations; useResultSummaries (inside features/results). Clear separation; no duplicate data-fetching hooks for the same resource.
- **components/ui:** LoadingBlock, PageLayout, ErrorAlert, EmptyState, StatusChip, StatCard, TraceabilityChip. Reused across pages. **Active.**
- **features/results/components:** Many (ResultsTable, ResultDetail*, ResultEvidencePanel, ResultReviewActions, etc.). Feature-specific; **Active.**

### 3.6 Legacy or disconnected areas

- **v1 getJobEntities:** Present in client and types; if no screen calls it, it is **candidate for removal** after backend contract audit.
- No obsolete pages or routes were identified; all four pages are reachable from the described flow.

### 3.7 Structural pain points

- **features/** — Only `results` exists; inventories/aisles are at page/component level. Could be reorganized so that "inventories" and "aisles" are feature modules (Stage 7).
- **api/** — Flat; single client. Adequate for current size; consolidation already done.
- **utils/** — Mixed (apiErrors, status helpers, formatDate, resultRoutes). Could be grouped by domain (e.g. status, routing, format) in a later reorg.

## 4. Classification

| Area | Classification | Note |
|------|----------------|------|
| Pages | **Active** | All four in use |
| features/results | **Active** | Core result/position UI |
| components/ui, Create*Dialog, ExecutionLogPanel | **Active** | Shared or main flow |
| api/client.ts (v3) | **Active** | Primary surface |
| api/client.ts (getJobEntities v1) | **Active / Unclear** | Depends on consumer |
| types | **Active** | Aligned with backend |

## 5. Risks

- Removing getJobEntities or v1 types without confirming every consumer could break a screen or future use.
- Reorganizing features (e.g. moving inventory/aisle into features/) will touch many imports; should follow backend stabilization.

## 6. Recommendations

- Trace `getJobEntities` usage to a specific screen or remove if unused.
- Document that the only feature module is `results`; plan a target structure (e.g. features/inventories, features/aisles, features/results) for Stage 7.

## 7. Candidate next-stage actions

- **Stage 7 (Frontend reorg):** Define target folder layout; move pages/component logic into feature modules if desired; keep api/ and types centralized.
- **Stage 8 (Frontend optimization):** After contract audit, remove unused types or client functions (e.g. v1) and consolidate any duplicated loading/error handling.
