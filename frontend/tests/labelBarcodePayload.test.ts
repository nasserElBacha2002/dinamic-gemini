import { describe, expect, it } from 'vitest';
import {
  buildInventoryCodePayload,
  buildLabelBarcodePayload,
  INVENTORY_CODE_PAYLOAD_MAX_LENGTH,
  inventoryBarcodeModuleWidth,
  LABEL_BARCODE_PAYLOAD_MAX_LENGTH,
  LABEL_CODE_MAX_LENGTH,
  LabelBarcodePayloadError,
  normalizeLabelCode,
  normalizeLabelQuantity,
  parseInventoryCodePayload,
  parseLabelBarcodePayload,
  tryBuildLabelBarcodePayload,
} from '../src/features/clients/components/labelBarcodePayload';
import { buildLabelQrText, buildLabelScanPayload } from '../src/features/clients/components/labelPrintUtils';

describe('normalizeLabelCode / normalizeLabelQuantity', () => {
  it('trims outer spaces and keeps internal spaces in code', () => {
    expect(normalizeLabelCode('  AB C  ')).toBe('AB C');
    expect(normalizeLabelQuantity('  150  ')).toBe('150');
  });

  it('preserves leading zeros in code (not as number)', () => {
    expect(normalizeLabelCode('00123')).toBe('00123');
  });
});

describe('buildInventoryCodePayload / buildLabelBarcodePayload', () => {
  it('encodes code and quantity with pipe separator', () => {
    expect(
      buildLabelBarcodePayload({
        code: '32535235',
        quantity: '909',
      })
    ).toBe('32535235|909');
    expect(buildInventoryCodePayload({ code: '22294029014', quantity: '234' })).toBe(
      '22294029014|234'
    );
  });

  it('encodes alphanumeric codes with hyphens and spaces', () => {
    expect(buildLabelBarcodePayload({ code: 'ABC-123', quantity: '150' })).toBe('ABC-123|150');
    expect(buildLabelBarcodePayload({ code: 'AB C', quantity: '12' })).toBe('AB C|12');
  });

  it('rejects codes that contain the pipe separator', () => {
    expect(() => buildLabelBarcodePayload({ code: 'A|B', quantity: '1' })).toThrow(
      LabelBarcodePayloadError
    );
  });

  it('preserves leading zeros in code', () => {
    expect(buildLabelBarcodePayload({ code: '00123', quantity: '9' })).toBe('00123|9');
  });

  it('supports multi-digit quantities', () => {
    expect(buildLabelBarcodePayload({ code: 'X', quantity: '99999999' })).toBe('X|99999999');
  });

  it('rejects empty code', () => {
    expect(() => buildLabelBarcodePayload({ code: '  ', quantity: '1' })).toThrow(
      LabelBarcodePayloadError
    );
  });

  it('rejects empty quantity', () => {
    expect(() => buildLabelBarcodePayload({ code: 'A', quantity: '' })).toThrow(
      LabelBarcodePayloadError
    );
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
    const longCode = 'A'.repeat(LABEL_CODE_MAX_LENGTH + 1);
    expect(tryBuildLabelBarcodePayload({ code: longCode, quantity: '99999999' })).toBeNull();
    expect(LABEL_CODE_MAX_LENGTH).toBeGreaterThan(0);
  });

  it('tryBuild returns null instead of throwing', () => {
    expect(tryBuildLabelBarcodePayload({ code: '', quantity: '1' })).toBeNull();
  });
});

describe('parseInventoryCodePayload', () => {
  it('parses pipe payload into internal_code and quantity', () => {
    expect(parseInventoryCodePayload('22294029014|234')).toEqual({
      format: 'pipe',
      internal_code: '22294029014',
      quantity: '234',
    });
  });

  it('parses legacy DI1 barcode payloads', () => {
    expect(parseInventoryCodePayload('DI1|C=ABC-123|Q=150')).toEqual({
      format: 'di1',
      internal_code: 'ABC-123',
      quantity: '150',
    });
    expect(parseInventoryCodePayload('DI1|C=A%7CB%3DC%25D|Q=1')).toEqual({
      format: 'di1',
      internal_code: 'A|B=C%D',
      quantity: '1',
    });
  });

  it('keeps quantity null for legacy code-only scans', () => {
    expect(parseInventoryCodePayload('32535235')).toEqual({
      format: 'plain',
      internal_code: '32535235',
      quantity: null,
    });
  });

  it('extracts code from legacy multiline human QR text', () => {
    const qr = buildLabelQrText({
      clientName: 'rabbione',
      supplierName: null,
      countedBy: null,
      code: '32535235',
      quantity: '909',
      lot: null,
      expiry: null,
      description: null,
      observations: null,
    });
    expect(parseInventoryCodePayload(qr)).toEqual({
      format: 'plain',
      internal_code: '32535235',
      quantity: null,
    });
  });
});

describe('parseLabelBarcodePayload', () => {
  it('round-trips builder output', () => {
    const payload = buildLabelBarcodePayload({ code: 'ABC-123', quantity: '150' });
    expect(parseLabelBarcodePayload(payload)).toEqual({
      version: 'PIPE',
      code: 'ABC-123',
      quantity: '150',
    });
  });

  it('still accepts legacy DI1', () => {
    expect(parseLabelBarcodePayload('DI1|C=A%7CB|Q=2')).toEqual({
      version: 'DI1',
      code: 'A|B',
      quantity: '2',
    });
  });

  it('rejects invalid DI1 version / fields', () => {
    expect(() => parseLabelBarcodePayload('DI0|C=A|Q=1')).toThrow(LabelBarcodePayloadError);
    expect(() => parseLabelBarcodePayload('DI1|Q=1')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|C=B|Q=1')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=1|Q=2')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=1|X=2')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=%E0%A4%A|Q=1')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=0')).toThrow();
    expect(() => parseLabelBarcodePayload('DI1|C=A|Q=1.5')).toThrow();
  });

  it('rejects empty payload and code-only when quantity is required', () => {
    expect(() => parseLabelBarcodePayload('')).toThrow();
    expect(() => parseLabelBarcodePayload('   ')).toThrow();
    expect(() => parseLabelBarcodePayload('ONLY-CODE')).toThrow();
  });
});

describe('QR and barcode consistency', () => {
  it('QR scan payload matches barcode payload (code|quantity)', () => {
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

    const scanPayload = buildLabelScanPayload(data);
    expect(scanPayload).toBe('32535235|909');
    expect(scanPayload).toBe(buildLabelBarcodePayload(data));

    const qrHuman = buildLabelQrText(data);
    expect(qrHuman).toContain(`Código interno: ${data.code}`);
    expect(qrHuman).toContain(`Cant. total: ${data.quantity}`);
  });
});

describe('payload max constant', () => {
  it('exposes a positive safe max length', () => {
    expect(LABEL_BARCODE_PAYLOAD_MAX_LENGTH).toBeGreaterThan(20);
    expect(INVENTORY_CODE_PAYLOAD_MAX_LENGTH).toBe(LABEL_BARCODE_PAYLOAD_MAX_LENGTH);
  });
});

describe('inventoryBarcodeModuleWidth', () => {
  it('gives thicker modules to short payloads than long ones at the same width', () => {
    const available = 983;
    const short = inventoryBarcodeModuleWidth('9909090832|1231', available);
    const long = inventoryBarcodeModuleWidth(`${'A'.repeat(40)}|99999999`, available);
    expect(short).not.toBeNull();
    expect(long).not.toBeNull();
    expect(short!).toBeGreaterThan(long!);
  });

  it('rejects silently-too-thin modules instead of clipping', () => {
    expect(inventoryBarcodeModuleWidth(`${'A'.repeat(48)}|99999999`, 40)).toBeNull();
  });
});
