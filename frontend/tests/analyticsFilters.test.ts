import { describe, it, expect } from 'vitest';
import {
  areAnalyticsFiltersEqual,
  createDefaultAnalyticsFilters,
  parseAnalyticsFiltersFromSearchParams,
  writeAnalyticsFiltersToSearchParams,
} from '../src/constants/analyticsFilters';

describe('analyticsFilters', () => {
  it('parseAnalyticsFiltersFromSearchParams reads filter query params', () => {
    const defaults = createDefaultAnalyticsFilters();
    const params = new URLSearchParams(
      'date_from=2026-04-19&date_to=2026-05-19&inventory_id=inv-1&aisle_id=a-1&provider_name=openai'
    );
    const parsed = parseAnalyticsFiltersFromSearchParams(params, defaults);
    expect(parsed.dateFrom).toBe('2026-04-19');
    expect(parsed.dateTo).toBe('2026-05-19');
    expect(parsed.inventoryId).toBe('inv-1');
    expect(parsed.aisleId).toBe('a-1');
    expect(parsed.providerName).toBe('openai');
  });

  it('ignores aisle_id when inventory_id is missing', () => {
    const defaults = createDefaultAnalyticsFilters();
    const parsed = parseAnalyticsFiltersFromSearchParams(
      new URLSearchParams('aisle_id=a-1'),
      defaults
    );
    expect(parsed.aisleId).toBe('');
  });

  it('falls back to defaults for invalid dates', () => {
    const defaults = createDefaultAnalyticsFilters();
    const parsed = parseAnalyticsFiltersFromSearchParams(
      new URLSearchParams('date_from=not-a-date&date_to=2026-13-40'),
      defaults
    );
    expect(parsed.dateFrom).toBe(defaults.dateFrom);
    expect(parsed.dateTo).toBe(defaults.dateTo);
  });

  it('writeAnalyticsFiltersToSearchParams omits empty values', () => {
    const defaults = createDefaultAnalyticsFilters();
    const written = writeAnalyticsFiltersToSearchParams(
      new URLSearchParams('tab=pasillos'),
      {
        ...defaults,
        inventoryId: 'inv-1',
        aisleId: 'a-1',
      },
      defaults
    );
    expect(written.get('inventory_id')).toBe('inv-1');
    expect(written.get('aisle_id')).toBe('a-1');
    expect(written.get('date_from')).toBeNull();
    expect(written.get('tab')).toBe('pasillos');
  });

  it('writeAnalyticsFiltersToSearchParams preserves unknown query params', () => {
    const defaults = createDefaultAnalyticsFilters();
    const written = writeAnalyticsFiltersToSearchParams(
      new URLSearchParams('tab=pasillos&foo=bar'),
      { ...defaults, inventoryId: 'inv-1' },
      defaults
    );
    expect(written.get('foo')).toBe('bar');
    expect(written.get('inventory_id')).toBe('inv-1');
    expect(written.get('tab')).toBe('pasillos');
  });

  it('areAnalyticsFiltersEqual compares all fields', () => {
    const a = createDefaultAnalyticsFilters();
    const b = { ...a, providerName: 'openai' };
    expect(areAnalyticsFiltersEqual(a, b)).toBe(false);
    expect(areAnalyticsFiltersEqual(a, { ...a })).toBe(true);
  });
});
