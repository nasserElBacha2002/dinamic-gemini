import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildLabelPrintFilename,
  buildLabelQrPayload,
  buildLabelQrValue,
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

  it('builds QR payload with all label fields', () => {
    expect(buildLabelQrPayload(sampleData, new Date('2026-05-15T12:00:00'))).toEqual({
      type: 'dinamic_inventory_label',
      version: 1,
      client: 'rabbione',
      supplier: 'etiqueta-a-mano',
      countedBy: '01',
      internalCode: '1931038',
      quantity: '03',
      lot: 'test',
      expiration: '1806',
      description: 'producto ejemplo',
      observations: 'observación',
      generatedAt: '2026-05-15',
    });
  });

  it('builds QR value as JSON with full label data', () => {
    const value = buildLabelQrValue(sampleData, new Date('2026-05-15T12:00:00'));
    const parsed = JSON.parse(value) as Record<string, string>;

    expect(parsed.client).toBe('rabbione');
    expect(parsed.supplier).toBe('etiqueta-a-mano');
    expect(parsed.countedBy).toBe('01');
    expect(parsed.internalCode).toBe('1931038');
    expect(parsed.quantity).toBe('03');
    expect(parsed.lot).toBe('test');
    expect(parsed.expiration).toBe('1806');
    expect(parsed.description).toBe('producto ejemplo');
    expect(parsed.observations).toBe('observación');
    expect(parsed.generatedAt).toBe('2026-05-15');
  });
});
