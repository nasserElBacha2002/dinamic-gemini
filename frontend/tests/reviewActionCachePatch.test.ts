import { describe, it, expect, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import {
  applyReviewActionToPositionSummary,
  patchCachesForAisleResultsStrategy,
} from '../src/hooks/reviewActionCachePatch';
import { mapPositionSummaryToResultSummary } from '../src/features/results/mappers/positionToResult';
import { computeResultsKpi } from '../src/features/results/selectors/resultsKpi';
import type { PositionSummary } from '../src/api/types/responses';
import { queryKeys } from '../src/api/queryKeys';
import {
  canonicalizeAislePositionsListQuery,
  positionsListKeyPart,
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
    expect(next.status).toBe('reviewed');
  });

  it('normalizes stale detected+confirmed cache shape to reviewed on confirm', () => {
    const stale = base({
      status: 'detected',
      needs_review: false,
      review_resolution: 'confirmed',
    });
    const next = applyReviewActionToPositionSummary(stale, { action_type: 'confirm' });
    expect(next).not.toBe(stale);
    expect(next.status).toBe('reviewed');
    expect(next.needs_review).toBe(false);
    expect(next.review_resolution).toBe('confirmed');
  });

  it('returns same reference when confirm repeats identical reviewed terminal state', () => {
    const already = base({
      status: 'reviewed',
      needs_review: false,
      review_resolution: 'confirmed',
    });
    const next = applyReviewActionToPositionSummary(already, { action_type: 'confirm' });
    expect(next).toBe(already);
  });

  it('maps update_quantity from request body (flat qty only)', () => {
    const next = applyReviewActionToPositionSummary(base(), {
      action_type: 'update_quantity',
      corrected_quantity: 42,
    });
    expect(next.qty).toBe(42);
    expect(next.corrected_quantity).toBe(42);
    expect(next.status).toBe('corrected');
    expect(next.review_resolution).toBe('qty_corrected');
    expect(next.needs_review).toBe(false);
    const mapped = mapPositionSummaryToResultSummary(next);
    expect(mapped.resolvedQty).toBe(42);
    expect(mapped.reviewStatus).toBe('CONFIRMED');
  });

  it('update_quantity patches nested quantity.final when quantity block exists', () => {
    const before = base({
      qty: 10,
      corrected_quantity: null,
      quantity: {
        detected: 10,
        final: 10,
        source: 'detected',
      },
    });
    const next = applyReviewActionToPositionSummary(before, {
      action_type: 'update_quantity',
      corrected_quantity: 20,
    });
    expect(next.quantity?.final).toBe(20);
    expect(next.quantity?.corrected).toBe(20);
    expect(mapPositionSummaryToResultSummary(next).resolvedQty).toBe(20);
    expect(computeResultsKpi([mapPositionSummaryToResultSummary(next)]).aisleTotalCounted).toBe(20);
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

  it('delete_position marks deleted but keeps mappable INVALID review status', () => {
    const next = applyReviewActionToPositionSummary(base(), { action_type: 'delete_position' });
    expect(next.status).toBe('deleted');
    expect(next.review_resolution).toBe('deleted');
    expect(next.needs_review).toBe(false);
    expect(mapPositionSummaryToResultSummary(next).reviewStatus).toBe('INVALID');
    expect(computeResultsKpi([mapPositionSummaryToResultSummary(next)]).aisleTotalCounted).toBe(0);
  });
});

describe('patchCachesForAisleResultsStrategy', () => {
  it('sets invalidatePositionsList when target row is absent', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', {
      page: 1,
      page_size: 20,
      job_slice: 'resolver_default',
    });
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

  it('delete_position keeps row in cached list as deleted/invalid', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plCanon = canonicalizeAislePositionsListQuery({});
    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', positionsListKeyPart(plCanon));
    qc.setQueryData(plKey, {
      positions: [base({ id: 'pos-1', qty: 20 })],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });

    const flags = patchCachesForAisleResultsStrategy(qc, 'inv-1', 'aisle-1', 'pos-1', {
      action_type: 'delete_position',
    });

    const list = qc.getQueryData<{ positions: PositionSummary[]; total_items: number }>(plKey);
    expect(flags.invalidatePositionsList).toBe(false);
    expect(list?.positions).toHaveLength(1);
    expect(list?.positions[0].status).toBe('deleted');
    expect(list?.positions[0].review_resolution).toBe('deleted');
    expect(mapPositionSummaryToResultSummary(list!.positions[0]).reviewStatus).toBe('INVALID');
    expect(list?.total_items).toBe(1);
    const kpi = computeResultsKpi(
      list!.positions.map(mapPositionSummaryToResultSummary)
    );
    expect(kpi.aisleTotalCounted).toBe(0);
  });

  it('update_quantity patches list cache for table and KPI', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const plCanon = canonicalizeAislePositionsListQuery({});
    const plKey = queryKeys.inventories.positionsList('inv-1', 'aisle-1', positionsListKeyPart(plCanon));
    qc.setQueryData(plKey, {
      positions: [
        base({
          id: 'pos-1',
          qty: 10,
          corrected_quantity: null,
          needs_review: true,
        }),
      ],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
      raw_fetch_truncated: false,
    });

    patchCachesForAisleResultsStrategy(qc, 'inv-1', 'aisle-1', 'pos-1', {
      action_type: 'update_quantity',
      corrected_quantity: 20,
    });

    const list = qc.getQueryData<{ positions: PositionSummary[] }>(plKey);
    expect(list?.positions[0].qty).toBe(20);
    expect(list?.positions[0].corrected_quantity).toBe(20);
    expect(list?.positions[0].status).toBe('corrected');
    const mapped = mapPositionSummaryToResultSummary(list!.positions[0]);
    expect(mapped.resolvedQty).toBe(20);
    expect(computeResultsKpi([mapped]).aisleTotalCounted).toBe(20);
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
