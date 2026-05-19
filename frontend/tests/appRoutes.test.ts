import { describe, it, expect } from 'vitest';
import { pathToAnalytics, pathToInventoryAnalyticsCompareMany } from '../src/constants/appRoutes';
import { parseAnalyticsTab } from '../src/constants/analyticsTabs';

describe('pathToAnalytics', () => {
  it('defaults to resumen tab', () => {
    expect(pathToAnalytics()).toBe('/analitica?tab=resumen');
  });

  it('maps internal tabs to URL query values', () => {
    expect(pathToAnalytics('costs')).toBe('/analitica?tab=costos');
    expect(pathToAnalytics('compare')).toBe('/analitica?tab=comparacion');
  });
});

describe('parseAnalyticsTab', () => {
  it('normalizes invalid tab to summary', () => {
    expect(parseAnalyticsTab('foo')).toBe('summary');
  });
});

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
