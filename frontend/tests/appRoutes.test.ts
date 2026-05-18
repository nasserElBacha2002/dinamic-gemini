import { describe, it, expect } from 'vitest';
import { pathToInventoryAnalyticsCompareMany } from '../src/constants/appRoutes';

describe('pathToInventoryAnalyticsCompareMany', () => {
  it('returns compare-many path without query when options are omitted', () => {
    expect(pathToInventoryAnalyticsCompareMany('inv-1')).toBe('/inventories/inv-1/analytics/compare-many');
  });

  it('appends aisleId query param when provided', () => {
    expect(pathToInventoryAnalyticsCompareMany('inv-1', { aisleId: 'a-1' })).toBe(
      '/inventories/inv-1/analytics/compare-many?aisleId=a-1'
    );
  });

  it('appends jobIds and baseline when provided', () => {
    expect(
      pathToInventoryAnalyticsCompareMany('inv-1', {
        aisleId: 'a-1',
        jobIds: ['j1', 'j2'],
        baseline: 'j1',
      })
    ).toBe('/inventories/inv-1/analytics/compare-many?aisleId=a-1&jobIds=j1%2Cj2&baseline=j1');
  });

  it('ignores blank aisleId, empty jobIds, and blank baseline', () => {
    expect(
      pathToInventoryAnalyticsCompareMany('inv-1', { aisleId: '   ', jobIds: [], baseline: ' ' })
    ).toBe('/inventories/inv-1/analytics/compare-many');
  });
});
