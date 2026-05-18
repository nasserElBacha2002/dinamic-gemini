import { describe, it, expect } from 'vitest';
import i18n from '../src/i18n';
import { mapCostWarnings } from '../src/features/analytics-dashboard/adapters/analyticsCostWarnings';

describe('mapCostWarnings', () => {
  it('translates known warning codes', () => {
    const warnings = mapCostWarnings(['PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE'], i18n.t);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]?.severity).toBe('info');
    expect(warnings[0]?.label).toContain('proveedor');
  });

  it('uses generic fallback for unknown codes', () => {
    const warnings = mapCostWarnings(['SOME_NEW_WARNING'], i18n.t);
    expect(warnings[0]?.label).toContain('SOME_NEW_WARNING');
  });
});
