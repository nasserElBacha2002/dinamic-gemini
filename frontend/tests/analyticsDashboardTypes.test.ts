import { describe, it, expect } from 'vitest';
import {
  buildFilterParams,
  getCompareEligibility,
  compareEligibilityTooltipKey,
} from '../src/features/analytics-dashboard/types';

describe('buildFilterParams', () => {
  const base = {
    dateFrom: '2026-01-01',
    dateTo: '2026-01-31',
    inventoryId: '',
    aisleId: '',
    clientId: '',
    clientSupplierId: '',
    providerName: '',
    modelName: '',
  };

  it('omits observability ISO dates when date inputs are empty', () => {
    const params = buildFilterParams({ ...base, dateFrom: '', dateTo: '' });
    expect(params.observability.from).toBeUndefined();
    expect(params.observability.to).toBeUndefined();
    expect(JSON.stringify(params.observability)).not.toContain('T00:00:00.000Z');
    expect(JSON.stringify(params.observability)).not.toContain('T23:59:59.999Z');
  });

  it('omits only cleared date fields', () => {
    const params = buildFilterParams({ ...base, dateFrom: '', dateTo: '2026-01-31' });
    expect(params.observability.from).toBeUndefined();
    expect(params.observability.to).toBe('2026-01-31T23:59:59.999Z');
  });

  it('builds observability ISO dates when both dates are set', () => {
    const params = buildFilterParams(base);
    expect(params.observability.from).toBe('2026-01-01T00:00:00.000Z');
    expect(params.observability.to).toBe('2026-01-31T23:59:59.999Z');
  });
});

describe('getCompareEligibility', () => {
  it('allows test inventories', () => {
    expect(getCompareEligibility('test')).toEqual({ allowed: true });
  });

  it('blocks unknown mode with unknown_mode reason', () => {
    expect(getCompareEligibility(undefined)).toEqual({ allowed: false, reason: 'unknown_mode' });
  });

  it('blocks non-test inventories with test_only reason', () => {
    expect(getCompareEligibility('production')).toEqual({ allowed: false, reason: 'test_only' });
  });
});

describe('compareEligibilityTooltipKey', () => {
  it('maps reasons to i18n keys', () => {
    expect(compareEligibilityTooltipKey('unknown_mode')).toBe('analyticsDashboard.compare.unknownModeTooltip');
    expect(compareEligibilityTooltipKey('test_only')).toBe('analyticsDashboard.compare.testOnlyTooltip');
  });
});
