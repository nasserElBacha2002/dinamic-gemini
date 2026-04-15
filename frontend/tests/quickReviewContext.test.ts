/**
 * Review queue → drawer context: ``jobId`` seeds GET position detail / evidence (read path).
 * POST ``/reviews`` ``job_id`` must come from the loaded detail row only (see QuickReviewDrawer).
 */

import { describe, it, expect } from 'vitest';
import { reviewQueueItemToContext } from '../src/features/reviewQueue/quickReviewContext';
import type { ReviewQueueItem } from '../src/api/types';

function minimalRow(overrides: Partial<ReviewQueueItem['position']> = {}): ReviewQueueItem {
  return {
    inventory_id: 'inv-1',
    inventory_name: 'Inv',
    aisle_code: 'A1',
    position: {
      id: 'pos-1',
      aisle_id: 'aisle-1',
      status: 'DETECTED',
      confidence: 0.9,
      needs_review: true,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
      position_code: 'P1',
      qty: 1,
      qtySource: 'detected',
      has_evidence: true,
      ...overrides,
    },
  };
}

describe('reviewQueueItemToContext', () => {
  it('sets jobId from position.job_id when present', () => {
    const ctx = reviewQueueItemToContext(minimalRow({ job_id: 'job-run-a' }), ['r1']);
    expect(ctx.jobId).toBe('job-run-a');
    expect(ctx.returnTo).toBe('review_queue');
  });

  it('omits jobId when position.job_id is absent', () => {
    const ctx = reviewQueueItemToContext(minimalRow(), ['r1']);
    expect(ctx.jobId).toBeUndefined();
  });

  it('trims whitespace on job_id', () => {
    const ctx = reviewQueueItemToContext(minimalRow({ job_id: '  job-x  ' }), []);
    expect(ctx.jobId).toBe('job-x');
  });
});
