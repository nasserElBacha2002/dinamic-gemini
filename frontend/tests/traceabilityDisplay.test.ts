/**
 * Epic 3 — Tests for visible traceability display mapper.
 */

import { describe, it, expect } from 'vitest';
import { visibleTraceabilityToApiStatus } from '../src/features/results/utils/traceabilityDisplay';

describe('visibleTraceabilityToApiStatus', () => {
  it('maps VALID to valid', () => {
    expect(visibleTraceabilityToApiStatus('VALID')).toBe('valid');
  });

  it('maps MISSING to missing', () => {
    expect(visibleTraceabilityToApiStatus('MISSING')).toBe('missing');
  });

  it('maps INVALID to invalid', () => {
    expect(visibleTraceabilityToApiStatus('INVALID')).toBe('invalid');
  });

  it('maps UNVALIDATED to unvalidated', () => {
    expect(visibleTraceabilityToApiStatus('UNVALIDATED')).toBe('unvalidated');
  });
});

describe('traceability chip labels (i18n)', () => {
  it('uses sent-frame id wording for valid status, not visual confirmation', async () => {
    const { default: i18n } = await import('../src/i18n');
    await i18n.changeLanguage('es');
    expect(i18n.t('traceability.valid')).toBe('ID presente en imágenes analizadas');
    expect(i18n.t('traceability.invalid')).toBe('ID no coincide con imágenes analizadas');
    expect(i18n.t('traceability.missing')).toBe('Sin ID de imagen');
    expect(i18n.t('traceability.unvalidated')).toBe('No validado');
    expect(i18n.t('traceability.valid')).not.toMatch(/^Válida$/i);
  });
});
