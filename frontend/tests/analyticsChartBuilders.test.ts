import { describe, it, expect } from 'vitest';
import { rankTopN } from '../src/features/analytics-dashboard/adapters/charting/sharedChartBuilders';
import { buildAisleEntityKey } from '../src/features/analytics-dashboard/adapters/aisleEntityKeys';
import { buildCostByAisleLookup } from '../src/features/analytics-dashboard/adapters/analyticsCostViewModel';

describe('rankTopN', () => {
  it('excludes null and invalid values', () => {
    const result = rankTopN({
      items: [
        { id: 'a', value: null, label: 'A' },
        { id: 'b', value: Number.NaN, label: 'B' },
        { id: 'c', value: 5, label: 'C' },
      ],
      getValue: (item) => item.value,
      getLabel: (item) => item.label,
      getId: (item) => item.id,
      formatDisplay: (value) => String(value),
    });
    expect(result).toHaveLength(1);
    expect(result[0]?.id).toBe('c');
  });

  it('includes zero only when includeZero is true', () => {
    const withoutZero = rankTopN({
      items: [{ id: 'z', value: 0, label: 'Zero' }],
      getValue: (item) => item.value,
      getLabel: (item) => item.label,
      getId: (item) => item.id,
      formatDisplay: (value) => String(value),
    });
    const withZero = rankTopN({
      items: [{ id: 'z', value: 0, label: 'Zero' }],
      getValue: (item) => item.value,
      getLabel: (item) => item.label,
      getId: (item) => item.id,
      formatDisplay: (value) => String(value),
      includeZero: true,
    });
    expect(withoutZero).toHaveLength(0);
    expect(withZero).toHaveLength(1);
  });
});

describe('buildAisleEntityKey', () => {
  it('avoids collisions for same aisle id across inventories', () => {
    const keyA = buildAisleEntityKey('inv-1', 'aisle-x');
    const keyB = buildAisleEntityKey('inv-2', 'aisle-x');
    expect(keyA).not.toBe(keyB);

    const lookup = buildCostByAisleLookup({
      scope: {},
      totals: {} as never,
      by_provider_model: [],
      by_inventory: [],
      by_aisle: [
        {
          inventory_id: 'inv-1',
          inventory_name: 'A',
          aisle_id: 'aisle-x',
          aisle_code: 'X',
          jobs_total: 1,
          jobs_with_cost: 1,
          total_cost: 1,
          total_counted_quantity: 1,
          cost_per_counted_unit: 1,
          total_execution_time_seconds: 1,
        },
        {
          inventory_id: 'inv-2',
          inventory_name: 'B',
          aisle_id: 'aisle-x',
          aisle_code: 'X',
          jobs_total: 1,
          jobs_with_cost: 1,
          total_cost: 2,
          total_counted_quantity: 2,
          cost_per_counted_unit: 2,
          total_execution_time_seconds: 2,
        },
      ],
      by_capture_status: [],
      warnings: [],
    });

    expect(lookup.get(keyA)?.total_cost).toBe(1);
    expect(lookup.get(keyB)?.total_cost).toBe(2);
  });
});
