/**
 * Targeted TanStack Query cache updates after POST .../reviews (no response body).
 * Patches derive only from the review request + known backend review_resolution strings.
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

/** Exported for unit tests — mirrors backend `PositionReviewResolution` string values. */
export function applyReviewActionToPositionSummary(
  position: PositionSummary,
  body: ReviewActionRequest
): PositionSummary {
  switch (body.action_type) {
    case 'confirm':
      return {
        ...position,
        needs_review: false,
        review_resolution: 'confirmed',
      };
    case 'update_quantity': {
      const q = body.corrected_quantity;
      if (typeof q !== 'number' || !Number.isFinite(q)) return position;
      return {
        ...position,
        needs_review: false,
        review_resolution: 'qty_corrected',
        qty: q,
        corrected_quantity: q,
        quantity: position.quantity
          ? {
              ...position.quantity,
              corrected: q,
              final: q,
              resolved: true,
              source: 'manual_review',
            }
          : {
              detected: q,
              corrected: q,
              final: q,
              source: 'manual_review',
            },
      };
    }
    case 'update_sku': {
      const sku = body.sku?.trim() ?? '';
      if (!sku) return position;
      return {
        ...position,
        needs_review: false,
        review_resolution: 'sku_corrected',
        sku,
        product: position.product
          ? { ...position.product, sku }
          : { sku, identity_source: 'primary_product' },
      };
    }
    case 'update_position_code': {
      const code = body.position_code?.trim() ?? '';
      if (!code) return position;
      return {
        ...position,
        needs_review: false,
        review_resolution: 'position_code_corrected',
        position_code: code,
      };
    }
    case 'mark_unknown':
      return {
        ...position,
        needs_review: false,
        review_resolution: 'unknown',
      };
    case 'mark_image_mismatch':
      return {
        ...position,
        needs_review: false,
        review_resolution: 'image_mismatch',
      };
    case 'delete_position':
      return {
        ...position,
        status: 'deleted',
        needs_review: false,
        review_resolution: 'deleted',
      };
    default:
      return position;
  }
}

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

  const nextItems = old.items.slice();
  nextItems[idx] = {
    ...old.items[idx],
    position: applyReviewActionToPositionSummary(old.items[idx].position, body),
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

  const next = old.positions.slice();
  next[idx] = applyReviewActionToPositionSummary(next[idx], body);
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
    queryClient.removeQueries({ queryKey: detailKey });
    return true;
  }

  let changed = false;
  queryClient.setQueriesData<PositionDetailResponse>(
    { queryKey: queryKeys.inventories.positionDetail(inventoryId, aisleId, positionId) },
    (old) => {
      if (!old) return old;
      changed = true;
      return {
        ...old,
        position: applyReviewActionToPositionSummary(old.position, body),
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
