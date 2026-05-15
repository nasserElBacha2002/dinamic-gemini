import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildLabelPrintFilename,
  buildLabelQrText,
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

describe('labelPrintUtils QR helpers', () => {
  const sampleData = {
    clientName: 'rabbione',
    supplierName: 'etiqueta-a-mano',
    countedBy: '01',
    code: '1931038',
    quantity: '03',
    lot: 'test',
    expiry: '1806',
    description: 'producto ejemplo',
    observations: 'observación',
    copies: 1,
  };

  it('builds QR text with all label fields as readable plain text', () => {
    const value = buildLabelQrText(sampleData, new Date('2026-05-15T12:00:00'));

    expect(value).toContain('ETIQUETA DINAMIC INVENTORY');
    expect(value).toContain('Cliente: rabbione');
    expect(value).toContain('Proveedor: etiqueta-a-mano');
    expect(value).toContain('Contado por: 01');
    expect(value).toContain('Código interno: 1931038');
    expect(value).toContain('Cant. total: 03');
    expect(value).toContain('Lote: test');
    expect(value).toContain('VTO: 1806');
    expect(value).toContain('Descripción: producto ejemplo');
    expect(value).toContain('Observaciones: observación');
    expect(value).toContain('Generado: 2026-05-15');

    expect(() => JSON.parse(value)).toThrow();
  });
});
