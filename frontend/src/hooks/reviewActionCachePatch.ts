/**
 * Targeted TanStack Query cache updates after POST .../reviews (no response body).
 * Patches derive only from the review request + known backend review_resolution strings.
 * Nested server-owned shapes (e.g. full `quantity` blocks) are not invented here — GET remains authoritative.
 */

import type { QueryClient } from '@tanstack/react-query';
import type { ReviewActionRequest } from '../api/types/requests';
import { REVIEW_ACTION_WIRE } from '../api/types/shared';
import type {
  PositionDetailResponse,
  PositionListResponse,
  PositionSummary,
} from '../api/types/responses';
import { queryKeys } from '../api/queryKeys';
import { recordReviewActionCacheObs } from '../dev/cacheMutationObservability';

/**
 * Post-success cache behavior for `useSubmitReviewAction`.
 *
 * - **`aisleResults`**: wired from `QuickReviewDrawer` when reviewing from aisle results.
 * - **`detail`**: **Reserved — not used in production.** Implemented + unit-tested for a future
 *   position-detail-only entry (narrower invalidation than `aisleResults`, e.g. no merge-results churn).
 *   `QuickReviewDrawer` passes `aisleResults` | `undefined`. Wire `detail` only when
 *   product adds a route that needs this contract; otherwise leave `undefined` / `aisleResults`.
 */
export type ReviewMutationStrategy = 'aisleResults' | 'detail';

/**
 * Compare fields this module may change. Used to detect true no-ops so we do not treat
 * "new object, same semantics" as a successful patch (which would suppress invalidation incorrectly).
 */
function positionsSemanticallyEqualForPatch(a: PositionSummary, b: PositionSummary): boolean {
  if (a === b) return true;
  return (
    a.needs_review === b.needs_review &&
    (a.review_resolution ?? null) === (b.review_resolution ?? null) &&
    a.qty === b.qty &&
    (a.corrected_quantity ?? null) === (b.corrected_quantity ?? null) &&
    (a.sku ?? null) === (b.sku ?? null) &&
    (a.product?.sku ?? null) === (b.product?.sku ?? null) &&
    a.position_code === b.position_code &&
    String(a.status) === String(b.status)
  );
}

/**
 * Exported for unit tests — mirrors backend `PositionReviewResolution` string values.
 * Only sets flat / explicitly requested fields; does not fabricate nested quantity provenance.
 */
export function applyReviewActionToPositionSummary(
  position: PositionSummary,
  body: ReviewActionRequest
): PositionSummary {
  let next: PositionSummary;
  switch (body.action_type) {
    case REVIEW_ACTION_WIRE.CONFIRM:
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'confirmed',
      };
      break;
    case REVIEW_ACTION_WIRE.UPDATE_QUANTITY: {
      const q = body.corrected_quantity;
      if (typeof q !== 'number' || !Number.isFinite(q)) return position;
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'qty_corrected',
        qty: q,
        corrected_quantity: q,
      };
      break;
    }
    case REVIEW_ACTION_WIRE.UPDATE_SKU: {
      const sku = body.sku?.trim() ?? '';
      if (!sku) return position;
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'sku_corrected',
        sku,
        ...(position.product ? { product: { ...position.product, sku } } : {}),
      };
      break;
    }
    case REVIEW_ACTION_WIRE.UPDATE_POSITION_CODE: {
      const code = body.position_code?.trim() ?? '';
      if (!code) return position;
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'position_code_corrected',
        position_code: code,
      };
      break;
    }
    case REVIEW_ACTION_WIRE.MARK_UNKNOWN:
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'unknown',
      };
      break;
    case REVIEW_ACTION_WIRE.MARK_IMAGE_MISMATCH:
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'image_mismatch',
      };
      break;
    case REVIEW_ACTION_WIRE.DELETE_POSITION:
      next = {
        ...position,
        status: 'deleted',
        needs_review: false,
        review_resolution: 'deleted',
      };
      break;
    default:
      return position;
  }
  return positionsSemanticallyEqualForPatch(position, next) ? position : next;
}

function transformPositionList(
  old: PositionListResponse,
  positionId: string,
  body: ReviewActionRequest
): PositionListResponse {
  if (!Array.isArray(old.positions)) return old;
  const idx = old.positions.findIndex((p) => p.id === positionId);
  if (idx === -1) return old;

  if (body.action_type === REVIEW_ACTION_WIRE.DELETE_POSITION) {
    const positions = old.positions.filter((p) => p.id !== positionId);
    const removed = old.positions.length - positions.length;
    if (removed === 0) return old;
    const totalItems = Math.max(0, old.total_items - removed);
    const totalPages =
      old.page_size && old.page_size > 0
        ? Math.max(1, Math.ceil(totalItems / old.page_size))
        : old.total_pages;
    return {
      ...old,
      positions,
      total_items: totalItems,
      total_pages: totalPages,
    };
  }

  const patched = applyReviewActionToPositionSummary(old.positions[idx], body);
  if (patched === old.positions[idx]) return old;

  const next = old.positions.slice();
  next[idx] = patched;
  return { ...old, positions: next };
}

function patchPositionDetailQueries(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): boolean {
  const detailKey = queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId);

  if (body.action_type === REVIEW_ACTION_WIRE.DELETE_POSITION) {
    const hadCachedDetail = queryClient
      .getQueryCache()
      .findAll({ queryKey: detailKey })
      .some((q) => q.state.data !== undefined);
    if (!hadCachedDetail) return false;
    // Drop detail cache entries so nothing re-renders a deleted row; avoids a refetch that would 404
    // or show stale evidence. A fresh load after navigation uses list/other queries instead.
    queryClient.removeQueries({ queryKey: detailKey });
    return true;
  }

  let changed = false;
  queryClient.setQueriesData<PositionDetailResponse>(
    { queryKey: detailKey },
    (old) => {
      if (!old) return old;
      const nextPos = applyReviewActionToPositionSummary(old.position, body);
      if (nextPos === old.position) return old;
      changed = true;
      return {
        ...old,
        position: nextPos,
      };
    }
  );
  return changed;
}

function patchAislePositionsLists(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): boolean {
  let changed = false;
  queryClient.setQueriesData<PositionListResponse>(
    { queryKey: queryKeys.inventories.positions(inventoryId, aisleId) },
    (old) => {
      if (!old || !Array.isArray(old.positions)) return old;
      const next = transformPositionList(old, positionId, body);
      if (next !== old) changed = true;
      return next;
    }
  );
  return changed;
}

export type ReviewCachePatchFlags = {
  /** When true, caller should invalidate position detail (nothing to patch/remove in cache). */
  invalidatePositionDetail: boolean;
  /** When true, caller should invalidate aisle positions list queries. */
  invalidatePositionsList: boolean;
};

function invalidatePositionDetail(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  positionId: string
) {
  queryClient.invalidateQueries({
    queryKey: queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId),
  });
}

/**
 * Apply cache patches for `aisleResults` strategy; merge-results still invalidated by caller.
 */
export function patchCachesForAisleResultsStrategy(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): ReviewCachePatchFlags {
  const listPatched = patchAislePositionsLists(queryClient, inventoryId, aisleId, positionId, body);
  const detailPatched = patchPositionDetailQueries(queryClient, inventoryId, aisleId, positionId, body);

  return {
    invalidatePositionDetail: !detailPatched,
    invalidatePositionsList: !listPatched,
  };
}

/**
 * Apply cache patches for `detail` strategy (no merge-results domain).
 */
export function patchCachesForDetailStrategy(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): ReviewCachePatchFlags {
  const listPatched = patchAislePositionsLists(queryClient, inventoryId, aisleId, positionId, body);
  const detailPatched = patchPositionDetailQueries(queryClient, inventoryId, aisleId, positionId, body);

  return {
    invalidatePositionDetail: !detailPatched,
    invalidatePositionsList: !listPatched,
  };
}

type ApplySubmitReviewActionCacheEffectsParams = {
  queryClient: QueryClient;
  inventoryId: string;
  aisleId: string;
  positionId: string;
  body: ReviewActionRequest;
  strategy?: ReviewMutationStrategy;
};

/**
 * Centralized strategy orchestration for review-action post-success behavior.
 * Keeps mutation hook lean and guarantees one convention for:
 * - conservative patching
 * - conditional fallback invalidation
 * - explicit domain invalidation boundaries per strategy
 */
export function applySubmitReviewActionCacheEffects({
  queryClient,
  inventoryId,
  aisleId,
  positionId,
  body,
  strategy,
}: ApplySubmitReviewActionCacheEffectsParams): void {
  if (strategy === 'aisleResults') {
    const flags = patchCachesForAisleResultsStrategy(
      queryClient,
      inventoryId,
      aisleId,
      positionId,
      body
    );
    const patchHits: Array<'position_detail' | 'positions_list'> = [];
    if (!flags.invalidatePositionsList) patchHits.push('positions_list');
    if (!flags.invalidatePositionDetail) patchHits.push('position_detail');
    const fallbackInvalidations: string[] = [];
    if (flags.invalidatePositionDetail) fallbackInvalidations.push('positionDetail');
    if (flags.invalidatePositionsList) fallbackInvalidations.push('positions(prefix)');
    if (flags.invalidatePositionDetail) {
      invalidatePositionDetail(queryClient, inventoryId, aisleId, positionId);
    }
    if (flags.invalidatePositionsList) {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
      });
    }
    queryClient.invalidateQueries({
      queryKey: queryKeys.inventories.mergeResults(inventoryId, aisleId),
    });
    recordReviewActionCacheObs({
      strategy: 'aisleResults',
      scope: { inventoryId, aisleId, positionId },
      patchHits,
      fallbackInvalidations,
      directInvalidations: ['mergeResults'],
    });
    return;
  }

  // Detail flows often sit beside a parent positions list (same aisle); refreshing that list keeps row
  // summaries and counts aligned with the reviewed position without touching merge-results.
  if (strategy === 'detail') {
    const flags = patchCachesForDetailStrategy(queryClient, inventoryId, aisleId, positionId, body);
    const patchHits: Array<'position_detail' | 'positions_list'> = [];
    if (!flags.invalidatePositionsList) patchHits.push('positions_list');
    if (!flags.invalidatePositionDetail) patchHits.push('position_detail');
    const fallbackInvalidations: string[] = [];
    if (flags.invalidatePositionDetail) fallbackInvalidations.push('positionDetail');
    if (flags.invalidatePositionsList) fallbackInvalidations.push('positions(prefix)');
    if (flags.invalidatePositionDetail) {
      invalidatePositionDetail(queryClient, inventoryId, aisleId, positionId);
    }
    if (flags.invalidatePositionsList) {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
      });
    }
    recordReviewActionCacheObs({
      strategy: 'detail',
      scope: { inventoryId, aisleId, positionId },
      patchHits,
      fallbackInvalidations,
      directInvalidations: [],
    });
    return;
  }

  // Default behavior (Phase 3 compatibility) for call sites that do not pass a strategy.
  recordReviewActionCacheObs({
    strategy: 'default',
    scope: { inventoryId, aisleId, positionId },
    patchHits: [],
    fallbackInvalidations: [],
    directInvalidations: [
      'positionDetail',
      'positions',
      'mergeResults',
      'aisles',
    ],
  });
  invalidatePositionDetail(queryClient, inventoryId, aisleId, positionId);
  queryClient.invalidateQueries({
    queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
  });
  queryClient.invalidateQueries({
    queryKey: queryKeys.inventories.mergeResults(inventoryId, aisleId),
  });
  queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
}
