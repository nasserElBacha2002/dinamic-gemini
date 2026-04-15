/**
 * Targeted TanStack Query cache updates after POST .../reviews (no response body).
 * Patches derive only from the review request + known backend review_resolution strings.
 * Nested server-owned shapes (e.g. full `quantity` blocks) are not invented here — GET remains authoritative.
 */

import type { QueryClient } from '@tanstack/react-query';
import type { ReviewActionRequest } from '../api/types/requests';
import type {
  PositionDetailResponse,
  PositionListResponse,
  PositionSummary,
  ReviewQueueListResponse,
} from '../api/types/responses';
import { queryKeys } from '../api/queryKeys';

export type ReviewMutationStrategy = 'reviewQueue' | 'aisleResults' | 'detail';

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
    case 'confirm':
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'confirmed',
      };
      break;
    case 'update_quantity': {
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
    case 'update_sku': {
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
    case 'update_position_code': {
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
    case 'mark_unknown':
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'unknown',
      };
      break;
    case 'mark_image_mismatch':
      next = {
        ...position,
        needs_review: false,
        review_resolution: 'image_mismatch',
      };
      break;
    case 'delete_position':
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

/**
 * After removing a row from a cached page, `total_items` / `total_pages` are best-effort local
 * approximations for UX (pagination may not match server totals under filters); exact counts come from refetch.
 */
function transformReviewQueueList(
  old: ReviewQueueListResponse,
  positionId: string,
  body: ReviewActionRequest
): ReviewQueueListResponse {
  if (!Array.isArray(old.items)) return old;
  const idx = old.items.findIndex((it) => it.position.id === positionId);
  if (idx === -1) return old;

  const removeRow =
    body.action_type === 'delete_position' ||
    body.action_type === 'confirm' ||
    body.action_type === 'mark_unknown' ||
    body.action_type === 'mark_image_mismatch';

  if (removeRow) {
    const items = old.items.filter((it) => it.position.id !== positionId);
    const removed = old.items.length - items.length;
    if (removed === 0) return old;
    const totalItems = Math.max(0, old.total_items - removed);
    const totalPages =
      old.page_size && old.page_size > 0
        ? Math.max(1, Math.ceil(totalItems / old.page_size))
        : old.total_pages;
    return {
      ...old,
      items,
      total_items: totalItems,
      total_pages: totalPages,
    };
  }

  const patched = applyReviewActionToPositionSummary(old.items[idx].position, body);
  if (patched === old.items[idx].position) return old;

  const nextItems = old.items.slice();
  nextItems[idx] = {
    ...old.items[idx],
    position: patched,
  };
  return { ...old, items: nextItems };
}

function transformPositionList(
  old: PositionListResponse,
  positionId: string,
  body: ReviewActionRequest
): PositionListResponse {
  if (!Array.isArray(old.positions)) return old;
  const idx = old.positions.findIndex((p) => p.id === positionId);
  if (idx === -1) return old;

  if (body.action_type === 'delete_position') {
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

function patchReviewQueueLists(
  queryClient: QueryClient,
  positionId: string,
  body: ReviewActionRequest
): boolean {
  let changed = false;
  queryClient.setQueriesData<ReviewQueueListResponse>(
    { queryKey: queryKeys.reviewQueue.all },
    (old) => {
      if (!old || !Array.isArray(old.items)) return old;
      const next = transformReviewQueueList(old, positionId, body);
      if (next !== old) changed = true;
      return next;
    }
  );
  return changed;
}

function patchPositionDetailQueries(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): boolean {
  const detailKey = queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId);

  if (body.action_type === 'delete_position') {
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
  /** When true, caller should still invalidate review-queue queries (no cached list or row not found). */
  invalidateReviewQueue: boolean;
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
 * Apply cache patches for `reviewQueue` strategy; narrow invalidation when patches hit cached data.
 */
export function patchCachesForReviewQueueStrategy(
  queryClient: QueryClient,
  inventoryId: string,
  aisleId: string,
  positionId: string,
  body: ReviewActionRequest
): ReviewCachePatchFlags {
  const queuePatched = patchReviewQueueLists(queryClient, positionId, body);
  const detailPatched = patchPositionDetailQueries(queryClient, inventoryId, aisleId, positionId, body);

  return {
    invalidateReviewQueue: !queuePatched,
    invalidatePositionDetail: !detailPatched,
    invalidatePositionsList: false,
  };
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
    invalidateReviewQueue: false,
    invalidatePositionDetail: !detailPatched,
    invalidatePositionsList: !listPatched,
  };
}

/**
 * Apply cache patches for `detail` strategy (no merge/review-queue domains).
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
    invalidateReviewQueue: false,
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
  // Review Queue screen (`ReviewQueuePage`) loads rows via `useReviewQueue` only; the drawer uses
  // `positionDetail`. Nothing on that route subscribes to aisle `positions`, merge-results, or `aisles`,
  // so invalidating those would only add redundant traffic after a review action.
  if (strategy === 'reviewQueue') {
    const flags = patchCachesForReviewQueueStrategy(
      queryClient,
      inventoryId,
      aisleId,
      positionId,
      body
    );
    if (flags.invalidatePositionDetail) {
      invalidatePositionDetail(queryClient, inventoryId, aisleId, positionId);
    }
    if (flags.invalidateReviewQueue) {
      queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue.all });
    }
    return;
  }

  if (strategy === 'aisleResults') {
    const flags = patchCachesForAisleResultsStrategy(
      queryClient,
      inventoryId,
      aisleId,
      positionId,
      body
    );
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
    return;
  }

  // Detail flows often sit beside a parent positions list (same aisle); refreshing that list keeps row
  // summaries and counts aligned with the reviewed position without touching merge/review-queue domains.
  if (strategy === 'detail') {
    const flags = patchCachesForDetailStrategy(queryClient, inventoryId, aisleId, positionId, body);
    if (flags.invalidatePositionDetail) {
      invalidatePositionDetail(queryClient, inventoryId, aisleId, positionId);
    }
    if (flags.invalidatePositionsList) {
      queryClient.invalidateQueries({
        queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
      });
    }
    return;
  }

  // Default behavior (Phase 3 compatibility) for call sites that do not pass a strategy.
  invalidatePositionDetail(queryClient, inventoryId, aisleId, positionId);
  queryClient.invalidateQueries({
    queryKey: queryKeys.inventories.positions(inventoryId, aisleId),
  });
  queryClient.invalidateQueries({
    queryKey: queryKeys.inventories.mergeResults(inventoryId, aisleId),
  });
  queryClient.invalidateQueries({ queryKey: queryKeys.inventories.aisles(inventoryId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.reviewQueue.all });
}
