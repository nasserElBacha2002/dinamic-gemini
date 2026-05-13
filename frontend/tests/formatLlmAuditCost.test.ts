import { describe, it, expect } from 'vitest';
import { formatAuditCostFromApiString, formatAuditTokenCount } from '../src/utils/formatLlmAuditCost';

describe('formatLlmAuditCost', () => {
  it('formats small USD amounts without collapsing to zero', () => {
    const s = formatAuditCostFromApiString('0.000123', 'USD', 'x');
    expect(s).not.toBe('x');
    expect(s).toMatch(/0[,.]000123/);
  });

  it('returns notReported for invalid decimal strings', () => {
    expect(formatAuditCostFromApiString('', 'USD', 'n/a')).toBe('n/a');
    expect(formatAuditCostFromApiString(null, 'USD', 'n/a')).toBe('n/a');
  });

  it('formats token counts with grouping', () => {
    expect(formatAuditTokenCount(12430, '—')).toMatch(/12[.,]430/);
  });
});
