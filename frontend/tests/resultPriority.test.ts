import { describe, it, expect } from 'vitest';
import { deriveResultPriority, sortResultsByPriority } from '../src/features/results/utils/resultPriority';
import type { ResultSummary } from '../src/features/results/types';
import { LOW_CONFIDENCE_THRESHOLD } from '../src/features/results/constants';

function base(overrides: Partial<ResultSummary> = {}): ResultSummary {
  return {
    id: 'x',
    sku: 'S',
    detectedQty: 2,
    correctedQty: null,
    resolvedQty: null,
    confidence: 0.9,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'VALID',
    needsReview: true,
    updatedAt: '2024-01-01T00:00:00Z',
    hasEvidence: true,
    ...overrides,
  };
}

describe('deriveResultPriority', () => {
  it('P1 when needs review and invalid traceability', () => {
    expect(deriveResultPriority(base({ traceabilityStatus: 'INVALID' })).tier).toBe(1);
  });

  it('P1 when needs review and missing evidence', () => {
    expect(deriveResultPriority(base({ hasEvidence: false })).tier).toBe(1);
  });

  it('P2 when needs review and low confidence', () => {
    expect(
      deriveResultPriority(
        base({ confidence: LOW_CONFIDENCE_THRESHOLD - 0.01, traceabilityStatus: 'VALID' })
      ).tier
    ).toBe(2);
  });

  it('P2 when needs review and qty zero', () => {
    expect(deriveResultPriority(base({ detectedQty: 0, resolvedQty: null })).tier).toBe(2);
  });

  it('P3 when needs review only', () => {
    expect(deriveResultPriority(base()).tier).toBe(3);
  });

  it('P4 when not needs review', () => {
    expect(deriveResultPriority(base({ needsReview: false })).tier).toBe(4);
  });
});

describe('sortResultsByPriority', () => {
  it('orders P1 before P4', () => {
    const rows = [base({ id: 'a', needsReview: false }), base({ id: 'b', traceabilityStatus: 'INVALID' })];
    const sorted = sortResultsByPriority(rows);
    expect(sorted[0].id).toBe('b');
    expect(sorted[1].id).toBe('a');
  });
});
