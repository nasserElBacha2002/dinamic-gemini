import { describe, it, expect } from 'vitest';
import { formatLlmCostAmount, formatMetricValue } from '../src/features/analytics-dashboard/adapters/analyticsCostFormatters';

describe('analyticsCostFormatters', () => {
  it('formats LLM cost without currency prefix', () => {
    expect(formatLlmCostAmount(24.82)).toMatch(/24[,.]82/);
    expect(formatLlmCostAmount(24.82)).not.toMatch(/US\$/);
  });

  it('formats integers with locale grouping', () => {
    expect(formatMetricValue(1250, 'integer')).toMatch(/1[,.]250/);
  });

  it('returns placeholder for non-finite values', () => {
    expect(formatMetricValue(Number.NaN, 'cost')).toBe('—');
    expect(formatMetricValue(Number.POSITIVE_INFINITY, 'integer')).toBe('—');
  });
});
