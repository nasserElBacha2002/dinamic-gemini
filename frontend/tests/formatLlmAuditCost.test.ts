import { describe, it, expect } from 'vitest';
import {
  formatAuditCostFromApiString,
  formatAuditTokenCount,
  normalizeCurrency,
} from '../src/utils/formatLlmAuditCost';

describe('formatLlmAuditCost', () => {
  it('formats small USD amounts without collapsing to zero', () => {
    const s = formatAuditCostFromApiString('0.000123', 'USD', 'x');
    expect(s).not.toBe('x');
    expect(s).toMatch(/0[,.]000123/);
    const collapsedZero = new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(0);
    expect(s).not.toBe(collapsedZero);
    expect(s).not.toMatch(/^(\s|US\$|\u00a0)*0[,.]00(\s|$)/);
  });

  it('normalizeCurrency returns USD for non-strings and invalid codes', () => {
    expect(normalizeCurrency(null)).toBe('USD');
    expect(normalizeCurrency(123)).toBe('USD');
    expect(normalizeCurrency('us')).toBe('USD');
    expect(normalizeCurrency('  eur  ')).toBe('EUR');
  });

  it('returns notReported for invalid decimal strings', () => {
    expect(formatAuditCostFromApiString('', 'USD', 'n/a')).toBe('n/a');
    expect(formatAuditCostFromApiString(null, 'USD', 'n/a')).toBe('n/a');
  });

  it('formats token counts with grouping', () => {
    expect(formatAuditTokenCount(12430, '—')).toMatch(/12[.,]430/);
  });
});
