import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildLabelPrintFilename,
  sanitizeLabelFilenameSegment,
} from '../src/features/clients/components/labelPrintUtils';

describe('labelPrintUtils filename helpers', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-15T12:00:00'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sanitizes filename segments', () => {
    expect(sanitizeLabelFilenameSegment('Cliente Norte', 'cliente')).toBe('cliente-norte');
    expect(sanitizeLabelFilenameSegment('Rabbione S.A.', 'cliente')).toBe('rabbione-s-a');
    expect(sanitizeLabelFilenameSegment('Cód 05/7', 'codigo')).toBe('cod-05-7');
    expect(sanitizeLabelFilenameSegment('03 unidades', 'cantidad')).toBe('03-unidades');
    expect(sanitizeLabelFilenameSegment('', 'cliente')).toBe('cliente');
  });

  it('builds sanitized print filename with date suffix', () => {
    expect(
      buildLabelPrintFilename(
        { clientName: 'Cliente Norte', code: 'Cód 05/7', quantity: '03 unidades' },
        new Date('2026-05-15T12:00:00')
      )
    ).toBe('cliente-norte-cod-05-7-03-unidades-2026-05-15');

    expect(
      buildLabelPrintFilename(
        { clientName: 'Rabbione', code: '1931038', quantity: '03' },
        new Date('2026-05-15T12:00:00')
      )
    ).toBe('rabbione-1931038-03-2026-05-15');
  });
});
