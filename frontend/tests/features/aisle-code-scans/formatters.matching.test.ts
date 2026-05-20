import { describe, expect, it } from 'vitest';
import {
  formatCodeScanMatchStatus,
  formatCodeScanMatchType,
} from '../../../src/features/aisle-code-scans/formatters';

const t = (key: string) => {
  const map: Record<string, string> = {
    'aisleCodeScans.matching.matched': 'Coincidencia sugerida',
    'aisleCodeScans.matching.no_match': 'Sin coincidencia',
    'aisleCodeScans.matching.multiple_candidates': 'Coincidencia múltiple',
    'aisleCodeScans.matching.not_evaluated': 'No evaluado',
    'aisleCodeScans.matching.sku_exact': 'SKU exacto',
    'aisleCodeScans.matching.mixed': 'Coincidencia mixta',
  };
  return map[key] ?? key;
};

describe('code scan matching formatters', () => {
  it('formats match statuses in Spanish', () => {
    expect(formatCodeScanMatchStatus(t, 'matched')).toBe('Coincidencia sugerida');
    expect(formatCodeScanMatchStatus(t, 'no_match')).toBe('Sin coincidencia');
    expect(formatCodeScanMatchStatus(t, 'multiple_candidates')).toBe('Coincidencia múltiple');
  });

  it('formats match types', () => {
    expect(formatCodeScanMatchType(t, 'sku_exact')).toBe('SKU exacto');
  });

  it('formats mixed summary status', () => {
    expect(formatCodeScanMatchStatus(t, 'mixed')).toBe('Coincidencia mixta');
  });
});
