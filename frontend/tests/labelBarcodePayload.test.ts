import { describe, expect, it } from 'vitest';
import {
  buildLabelBarcodePayload,
  LABEL_BARCODE_PAYLOAD_MAX_LENGTH,
  LABEL_CODE_MAX_LENGTH,
  LabelBarcodePayloadError,
  normalizeLabelCode,
  normalizeLabelQuantity,
  parseLabelBarcodePayload,
  tryBuildLabelBarcodePayload,
} from '../src/features/clients/components/labelBarcodePayload';
import { buildLabelQrText } from '../src/features/clients/components/labelPrintUtils';

describe('normalizeLabelCode / normalizeLabelQuantity', () => {
  it('trims outer spaces and keeps internal spaces in code', () => {
    expect(normalizeLabelCode('  AB C  ')).toBe('AB C');
    expect(normalizeLabelQuantity('  150  ')).toBe('150');
  });

  it('preserves leading zeros in code (not as number)', () => {
    expect(normalizeLabelCode('00123')).toBe('00123');
  });
});

describe('buildLabelBarcodePayload', () => {
  it('encodes code and quantity', () => {
    expect(
      buildLabelBarcodePayload({
        code: '32535235',
        quantity: '909',
      })
    ).toBe('DI1|C=32535235|Q=909');
  });

  it('encodes alphanumeric codes with hyphens', () => {
    expect(buildLabelBarcodePayload({ code: 'ABC-123', quantity: '150' })).toBe('DI1|C=ABC-123|Q=150');
  });

  it('keeps internal spaces and encodes special characters', () => {
    expect(buildLabelBarcodePayload({ code: 'AB C', quantity: '12' })).toBe('DI1|C=AB%20C|Q=12');
    expect(buildLabelBarcodePayload({ code: 'A|B=C%D', quantity: '1' })).toBe(
      'DI1|C=A%7CB%3DC%25D|Q=1'
    );
  });

  it('preserves leading zeros in code', () => {
    expect(buildLabelBarcodePayload({ code: '00123', quantity: '9' })).toBe('DI1|C=00123|Q=9');
  });

  it('supports multi-digit quantities', () => {
    expect(buildLabelBarcodePayload({ code: 'X', quantity: '99999999' })).toBe('DI1|C=X|Q=99999999');
  });

  it('rejects empty code', () => {
    expect(() => buildLabelBarcodePayload({ code: '  ', quantity: '1' })).toThrow(LabelBarcodePayloadError);
  });

  it('rejects empty quantity', () => {
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '' })).toThrow(LabelBarcodePayloadError);
  });

  it('rejects negative, decimal, thousand-separated, and leading-zero quantities', () => {
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '-1' })).toThrow();
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '1.5' })).toThrow();
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '1,000' })).toThrow();
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '03' })).toThrow();
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '0' })).toThrow();
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '1e3' })).toThrow();
  });

  it('rejects payloads that exceed the safe max length', () => {
    const specialHeavy = `${'A'.repeat(20)}${'|'.repeat(20)}`;
    expect(tryBuildLabelBarcodePayload({ code: specialHeavy, quantity: '99999999' })).toBeNull();
    expect(LABEL_CODE_MAX_LENGTH).toBeGreaterThan(0);
  });

  it('tryBuild returns null instead of throwing', () => {
    expect(tryBuildLabelBarcodePayload({ code: '', quantity: '1' })).toBeNull();
  });
});

describe('parseLabelBarcodePayload', () => {
  it('round-trips builder output', () => {
    const payload = buildLabelBarcodePayload({ code: 'ABC-123', quantity: '150' });
    expect(parseLabelBarcodePayload(payload)).toEqual({
      version: 'DI1',
      code: 'ABC-123',
      quantity: '150',
    });
  });

  it('decodes escaped code characters', () => {
    const payload = buildLabelBarcodePayload({ code: 'A|B=C', quantity: '2' });
    expect(parseLabelBarcodePayload(payload)).toEqual({
      version: 'DI1',
      code: 'A|B=C',
      quantity: '2',
    });
  });

  it('rejects invalid version', () => {
    expect(() => parseLabelBarcodePayload('DI0|C=A|Q=1')).toThrow(LabelBarcodePayloadError);
  });

  it('rejects missing C or Q', () => {
    expect(() => parseLabelBarcodePayload('DI1|Q=1')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A')).toThrow();
  });

  it('rejects duplicate fields', () => {
    expect(() => parseLabelBarcodePayload('DI1|C=A|C=B|Q=1')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=1|Q=2')).toThrow();
  });

  it('rejects unknown fields (strict policy)', () => {
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=1|X=2')).toThrow();
  });

  it('rejects invalid escape and invalid quantity', () => {
    expect(() => parseLabelBarcodePayload('DI1|C=%E0%A4%A|Q=1')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=0')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=1.5')).toThrow();
  });

  it('rejects empty payload', () => {
    expect(() => parseLabelBarcodePayload('')).toThrow();
    expect(() => parseLabelBarcodePayload('   ')).toThrow();
  });
});

describe('QR and barcode consistency', () => {
  it('barcode code/quantity match QR text fields', () => {
    const data = {
      clientName: 'rabbione',
      supplierName: 'etiqueta-a-mano',
      countedBy: null,
      code: '32535235',
      quantity: '909',
      lot: null,
      expiry: null,
      description: null,
      observations: null,
    };
    const barcode = parseLabelBarcodePayload(buildLabelBarcodePayload(data));
    expect(barcode.code).toBe(data.code.trim());
    expect(barcode.quantity).toBe(data.quantity.trim());

    const qr = buildLabelQrText(data);
    expect(qr).toContain(`Código interno: ${data.code}`);
    expect(qr).toContain(`Cant. total: ${data.quantity}`);
  });
});

describe('payload max constant', () => {
  it('exposes a positive safe max length', () => {
    expect(LABEL_BARCODE_PAYLOAD_MAX_LENGTH).toBeGreaterThan(20);
  });
});
