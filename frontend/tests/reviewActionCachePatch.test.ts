import { describe, it, expect } from 'vitest';
import { applyReviewActionToPositionSummary } from '../src/hooks/reviewActionCachePatch';
import type { PositionSummary } from '../src/api/types/responses';

function base(): PositionSummary {
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
  };
}

describe('applyReviewActionToPositionSummary', () => {
  it('maps confirm to confirmed resolution', () => {
    const next = applyReviewActionToPositionSummary(base(), { action_type: 'confirm' });
    expect(next.needs_review).toBe(false);
    expect(next.review_resolution).toBe('confirmed');
  });

  it('maps update_quantity from request body', () => {
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
});
