/** UI aggregate: one ProductRecord = one row; total = sum of quantities. */

import { describe, expect, it } from 'vitest';
import type { PositionSummary } from '../src/api/types';
import { expandPositionSummariesToProductRows } from '../src/features/results/mappers/positionToResult';
import { computeResultsKpi } from '../src/features/results/selectors/resultsKpi';
import { filterResults } from '../src/features/results/selectors/resultsFilters';
import type { ResultSummary } from '../src/features/results/types';

function makePosition(overrides: Partial<PositionSummary> & { id: string }): PositionSummary {
  const { id, ...rest } = overrides;
  return {
    id,
    aisle_id: 'aisle-1',
    status: 'detected',
    confidence: 0.9,
    needs_review: false,
    updated_at: '2026-08-10T00:00:00Z',
    created_at: '2026-08-10T00:00:00Z',
    ...rest,
  } as PositionSummary;
}

describe('physical multi-label cardinality', () => {
  it('expands two ProductRecords on one Position into two result rows', () => {
    const positions = [
      makePosition({
        id: 'pos-047',
        sku: '232424090',
        detected_quantity: 1000,
        qty: 1000,
        aisle_position_assigned: true,
        detected_products: [
          {
            product_record_id: 'pr-a',
            sku: '232424090',
            detected_quantity: 1000,
            corrected_quantity: null,
            label_id: '6YD0S6WVMM',
            qty_source: 'label_explicit',
          },
          {
            product_record_id: 'pr-b',
            sku: '232424025',
            detected_quantity: 1100,
            corrected_quantity: null,
            label_id: '6FYR11RPXS',
            qty_source: 'label_explicit',
          },
        ],
      }),
    ];
    const rows = expandPositionSummariesToProductRows(positions);
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.labelId)).toEqual(['6YD0S6WVMM', '6FYR11RPXS']);
    expect(rows.map((r) => r.resolvedQty)).toEqual([1000, 1100]);
    expect(rows.every((r) => r.sourcePositionId === 'pos-047')).toBe(true);
  });

  it('physical fixture totals: count=5 total=55251', () => {
    const qtys = [10009, 1000, 1000, 1100, 42142];
    const results: ResultSummary[] = qtys.map((q, i) => ({
      id: `pr-${i}`,
      sourcePositionId: `pos-${i}`,
      sku: `SKU-${i}`,
      labelId: `LABEL-${i}`,
      positionCode: null,
      detectedQty: q,
      correctedQty: null,
      resolvedQty: q,
      confidence: 0.9,
      reviewStatus: 'DETECTED',
      traceabilityStatus: 'VALID',
      needsReview: false,
      updatedAt: '2026-08-10T00:00:00Z',
      hasEvidence: true,
      hasValidEvidence: true,
      aislePositionAssigned: i % 2 === 0,
    }));
    const kpi = computeResultsKpi(results);
    expect(kpi.countableResults).toBe(5);
    expect(kpi.aisleTotalCounted).toBe(55251);

    const withPos = filterResults(results, 'with_position');
    const withoutPos = filterResults(results, 'without_position');
    expect(withPos).toHaveLength(3);
    expect(withoutPos).toHaveLength(2);
  });

  it('omits position-only rows from item count expansion', () => {
    const positions = [
      makePosition({
        id: 'pos-only',
        sku: undefined,
        detected_quantity: undefined,
        qty: undefined,
        detected_products: [],
      }),
    ];
    expect(expandPositionSummariesToProductRows(positions)).toHaveLength(0);
  });
});
