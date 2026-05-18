import { describe, it, expect } from 'vitest';
import { pathToInventoryAnalyticsCompareMany } from '../src/constants/appRoutes';

describe('pathToInventoryAnalyticsCompareMany', () => {
  it('returns compare-many path without query when aisleId is omitted', () => {
    expect(pathToInventoryAnalyticsCompareMany('inv-1')).toBe('/inventories/inv-1/analytics/compare-many');
  });

  it('appends aisleId query param when provided', () => {
    expect(pathToInventoryAnalyticsCompareMany('inv-1', { aisleId: 'a-1' })).toBe(
      '/inventories/inv-1/analytics/compare-many?aisleId=a-1'
    );
  });

  it('ignores blank aisleId', () => {
    expect(pathToInventoryAnalyticsCompareMany('inv-1', { aisleId: '   ' })).toBe(
      '/inventories/inv-1/analytics/compare-many'
    );
  });
});
