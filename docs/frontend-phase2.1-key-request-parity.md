# Frontend Phase 2.1 — Query Key / Request Payload Parity

## Goal

Ensure TanStack Query **cache keys** are a pure function of the **canonical request payload** sent to the API for:

- `useReviewQueue`
- `useAislePositions`

## Integer normalization policy

- **Rule:** `page` and `page_size` are **positive finite integers** (`>= 1`), with **truncation** via `Math.trunc` for fractional inputs.
- **Invalid** values (`NaN`, `Infinity`, `< 1`, non-number) are **omitted** from the canonical payload (aisle positions / review queue) or fall back to table defaults (inventories list only).
- **Enforcement:** `normalizePositiveInt` in `frontend/src/api/queryParamCanonicalization.ts`, exported for tests.

## Confidence numbers

- `min_confidence` / `max_confidence` use **finite** numbers only (`Number.isFinite`), excluding `Infinity` and `NaN`, so keys and wire params stay aligned.

## Files

- `canonicalizeReviewQueueListQuery` + `reviewQueueListKeyPart` (key derived from canonical semantics)
- `canonicalizeAislePositionsListQuery` + `positionsListKeyPart` (key derived from canonical semantics)
- Hooks: `useReviewQueue`, `useAislePositions` call `get*` with the same canonical object used for key materialization.

## Deferred (Phase 3+)

- Mutation invalidation scope / fan-out
- `setQueryData` cache patching
- Broader analytics key canonicalization
