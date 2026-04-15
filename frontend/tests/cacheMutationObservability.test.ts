import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import {
  clearCacheMutationObservabilityEvents,
  getCacheMutationObservabilityEvents,
  isCacheMutationObservabilityActive,
  recordExplicitRefreshObs,
  recordMutationInvalidationsObs,
  setCacheMutationObservabilityTestOverride,
  summarizeQueryKey,
} from '../src/dev/cacheMutationObservability';
import { applySubmitReviewActionCacheEffects } from '../src/hooks/reviewActionCachePatch';
import { queryKeys } from '../src/api/queryKeys';
import {
  canonicalizeReviewQueueListQuery,
  reviewQueueListKeyPart,
} from '../src/api/queryParamCanonicalization';
import type { PositionDetailResponse, PositionSummary, ReviewQueueListResponse } from '../src/api/types/responses';

function basePosition(overrides: Partial<PositionSummary> = {}): PositionSummary {
  return {
    id: 'pos-1',
    aisle_id: 'aisle-1',
    status: 'detected',
    confidence: 0.9,
    needs_review: true,
    position_code: 'P1',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    qty: 3,
    qtySource: 'detected',
    has_evidence: true,
    ...overrides,
  };
}

describe('cacheMutationObservability', () => {
  beforeEach(() => {
    clearCacheMutationObservabilityEvents();
    setCacheMutationObservabilityTestOverride(true);
  });

  afterEach(() => {
    setCacheMutationObservabilityTestOverride(null);
    clearCacheMutationObservabilityEvents();
  });

  it('is inactive in test mode without explicit override', () => {
    setCacheMutationObservabilityTestOverride(null);
    expect(isCacheMutationObservabilityActive()).toBe(false);
    recordMutationInvalidationsObs({ flow: 'useRunAisleMerge', labels: ['x'] });
    expect(getCacheMutationObservabilityEvents()).toHaveLength(0);
  });

  it('records explicit refresh and mutation invalidation summaries when override is on', () => {
    recordExplicitRefreshObs({
      flow: 'merge_merge_results',
      mechanism: 'fetchQuery',
      keySummary: 'v3 › inventories › …',
    });
    recordMutationInvalidationsObs({ flow: 'useCreateAisle', labels: ['inventories.detail'] });
    const ev = getCacheMutationObservabilityEvents();
    expect(ev).toHaveLength(2);
    expect(ev[0].kind).toBe('explicit_refresh');
    expect(ev[1].kind).toBe('mutation_invalidations');
  });

  it('summarizeQueryKey truncates long keys', () => {
    const k = ['v3', 'inventories', 'aisles', 'inv-1', 'positions', 'aisle-1', { page: 1 }, 'extra'];
    expect(summarizeQueryKey(k)).toContain('v3');
    expect(summarizeQueryKey(k)).toContain('[obj]');
  });

  it('applySubmitReviewActionCacheEffects emits review_action_cache for reviewQueue when patches hit', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const rqCanonical = canonicalizeReviewQueueListQuery({ page: 1, page_size: 25 });
    const rqKey = queryKeys.reviewQueue.list(reviewQueueListKeyPart(rqCanonical));
    qc.setQueryData(rqKey, {
      summary: {
        pending_review: 1,
        low_confidence: 0,
        invalid_traceability: 0,
        qty_zero: 0,
        missing_evidence: 0,
      },
      items: [
        {
          inventory_id: 'inv-1',
          inventory_name: 'Inv',
          aisle_code: 'A',
          position: basePosition(),
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    } satisfies ReviewQueueListResponse);

    const detailKey = queryKeys.inventories.positionDetailScoped('inv-1', 'aisle-1', 'pos-1', null, false);
    const detail: PositionDetailResponse = {
      position: basePosition(),
      evidences: [],
      review_actions: [],
      run_context: { result_context_source: 'legacy' },
    };
    qc.setQueryData(detailKey, detail);

    applySubmitReviewActionCacheEffects({
      queryClient: qc,
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      positionId: 'pos-1',
      body: { action_type: 'confirm' },
      strategy: 'reviewQueue',
    });

    const reviewEv = getCacheMutationObservabilityEvents().filter((e) => e.kind === 'review_action_cache');
    expect(reviewEv).toHaveLength(1);
    const row = reviewEv[0] as Extract<(typeof reviewEv)[number], { kind: 'review_action_cache' }>;
    expect(row.strategy).toBe('reviewQueue');
    expect(row.patchHits).toContain('review_queue_list');
    expect(row.patchHits).toContain('position_detail');
    expect(row.fallbackInvalidations).toHaveLength(0);
  });
});
