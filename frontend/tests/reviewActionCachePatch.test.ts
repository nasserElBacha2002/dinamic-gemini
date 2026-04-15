import { describe, it, expect, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import {
  applyReviewActionToPositionSummary,
  patchCachesForAisleResultsStrategy,
  patchCachesForReviewQueueStrategy,
} from '../src/hooks/reviewActionCachePatch';
import type { PositionSummary } from '../src/api/types/responses';
import { queryKeys } from '../src/api/queryKeys';
import {
  canonicalizeReviewQueueListQuery,
  reviewQueueListKeyPart,
} from '../src/api/queryParamCanonicalization';

function base(overrides: Partial<PositionSummary> = {}): PositionSummary {
  return {
    id: 'p1',
    aisle_id: 'a1',
    status: 'detected',
    confidence: 0.8,
    needs_review: true,
    position_code: 'X',
    created_at: 't',
    updated_at: 't',
    qty: 2,
    qtySource: 'detected',
    has_evidence: true,
    ...overrides,
  };
}

describe('applyReviewActionToPositionSummary', () => {
  it('maps confirm to confirmed resolution', () => {
    const next = applyReviewActionToPositionSummary(base(), { action_type: 'confirm' });
    expect(next.needs_review).toBe(false);
    expect(next.review_resolution).toBe('confirmed');
  });

  it('maps update_quantity from request body (flat qty only)', () => {
    const next = applyReviewActionToPositionSummary(base(), {
      action_type: 'update_quantity',
      corrected_quantity: 42,
    });
    expect(next.qty).toBe(42);
    expect(next.review_resolution).toBe('qty_corrected');
  });

  it('does not invent quantity when corrected_quantity is missing', () => {
    const b = base();
    const next = applyReviewActionToPositionSummary(b, { action_type: 'update_quantity' });
    expect(next).toBe(b);
  });

  it('returns same reference when update_sku is whitespace-only', () => {
    const b = base();
    const next = applyReviewActionToPositionSummary(b, { action_type: 'update_sku', sku: '   ' });
    expect(next).toBe(b);
  });

  it('returns same reference when update_position_code is empty', () => {
    const b = base();
    const next = applyReviewActionToPositionSummary(b, {
      action_type: 'update_position_code',
      position_code: '',
    });
    expect(next).toBe(b);
  });

  it('returns same reference when confirm would repeat identical terminal state', () => {
    const already = base({
      needs_review: false,
      review_resolution: 'confirmed',
    });
    const next = applyReviewActionToPositionSummary(already, { action_type: 'confirm' });
    expect(next).toBe(already);
  });
});

describe('patchCachesForReviewQueueStrategy row not found', () => {
  it('sets invalidateReviewQueue when target row is absent from cached list', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const rqCanonical = canonicalizeReviewQueueListQuery({ page: 1, page_size: 25 });
    const rqKey = queryKeys.reviewQueue.list(reviewQueueListKeyPart(rqCanonical));
    qc.setQueryData(rqKey, {
      summary: { pending_review: 1, low_confidence: 0, invalid_traceability: 0, qty_zero: 0, missing_evidence: 0 },
      items: [
        {
          inventory_id: 'inv-1',
          inventory_name: 'Inv',
          aisle_code: 'A',
          position: base(),
        },
      ],
      page: 1,
      page_size: 25,
      total_items: 1,
      total_pages: 1,
    });

    const flags = patchCachesForReviewQueueStrategy(qc, 'inv-1', 'aisle-1', 'missing-pos', {
      action_type: 'confirm',
    });

    expect(flags.invalidateReviewQueue).toBe(true);
    expect(flags.invalidatePositionDetail).toBe(true);
  });
});

describe('patchCachesForAisleResultsStrategy row not found', () => {
  it('sets invalidatePositionsList when target row is absent', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', { page: 1, page_size: 20, job_slice: 'resolver_default' });
    qc.setQueryData(plKey, {
      positions: [base()],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });

    const flags = patchCachesForAisleResultsStrategy(qc, 'inv-1', 'aisle-1', 'other-id', {
      action_type: 'confirm',
    });

    expect(flags.invalidatePositionsList).toBe(true);
  });
});

describe('delete_position detail cache', () => {
  it('removeQueries drops scoped detail entries; does not remove unrelated inventory', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const removeSpy = vi.spyOn(qc, 'removeQueries');

    const keyTarget = queryKeys.inventories.positionDetailScoped('inv-1', 'aisle-1', 'pos-1', null, false);
    const keyOther = queryKeys.inventories.positionDetailScoped('inv-2', 'aisle-1', 'pos-1', null, false);
    qc.setQueryData(keyTarget, {
      position: base({ id: 'pos-1' }),
      evidences: [],
      review_actions: [],
      run_context: { result_context_source: 'legacy' },
    });
    qc.setQueryData(keyOther, {
      position: base({ id: 'pos-1' }),
      evidences: [],
      review_actions: [],
      run_context: { result_context_source: 'legacy' },
    });

    patchCachesForAisleResultsStrategy(qc, 'inv-1', 'aisle-1', 'pos-1', { action_type: 'delete_position' });

    expect(removeSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.inventories.positionDetail('inv-1', 'aisle-1', 'pos-1'),
    });
    expect(qc.getQueryData(keyOther)).not.toBeUndefined();
  });
});
