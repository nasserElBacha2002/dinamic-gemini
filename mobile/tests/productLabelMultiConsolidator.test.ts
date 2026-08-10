import { consolidateCodeDetections } from '../src/core/codeDetectionConsolidator';
import { buildProductLabelPayload } from '../src/core/productLabelFormat';
import * as fs from 'fs';
import * as path from 'path';

describe('codeDetectionConsolidator multi D1', () => {
  it('returns 0..N product results', () => {
    const a = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SKU100',
      quantity: 4,
    });
    const b = buildProductLabelPayload({
      labelId: 'FGHJKMNPQR',
      internalCode: 'SKU200',
      quantity: 2,
    });
    const result = consolidateCodeDetections([
      { rawValue: a, symbology: 'CODE128', detectionIndex: 0 },
      { rawValue: b, symbology: 'CODE128', detectionIndex: 1 },
    ]);
    expect(result.status).toBe('RESOLVED_MULTI');
    expect(result.productResults).toHaveLength(2);
  });

  it('dedupes by label_id within image', () => {
    const a = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SKU100',
      quantity: 4,
    });
    const result = consolidateCodeDetections([
      { rawValue: a, symbology: 'CODE128', detectionIndex: 0 },
      { rawValue: a, symbology: 'CODE128', detectionIndex: 1 },
    ]);
    expect(result.productResults).toHaveLength(1);
    expect(result.productResults[0]?.duplicateDetectionCount).toBe(2);
  });

  it('invalid D1 does not revive via legacy barcode', () => {
    const vectors = JSON.parse(
      fs.readFileSync(
        path.resolve(__dirname, '../../contracts/product-labels/v1/checksum-vectors.json'),
        'utf8',
      ),
    ) as { vectors: Array<{ name: string; tampered_payload?: string }> };
    const tampered = vectors.vectors.find((v) => v.name === 'checksum-fail-tampered-qty')!;
    const result = consolidateCodeDetections([
      {
        rawValue: tampered.tampered_payload as string,
        symbology: 'QR_CODE',
        detectionIndex: 0,
      },
      { rawValue: 'SKU123|1000', symbology: 'CODE_128', detectionIndex: 1 },
    ]);
    expect(result.status).toBe('NO_VALID_CODE');
    expect(result.warnings).toContain('D1_CANDIDATES_FAILED');
    expect(result.productResults).toHaveLength(0);
    expect(result.rejections.some((r) => r.validationStatus === 'D1_CHECKSUM_FAILED')).toBe(true);
  });

  it('same SKU different label_id → 2 product results', () => {
    const a = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SAME_SKU',
      quantity: 10,
    });
    const b = buildProductLabelPayload({
      labelId: 'FGHJKMNPQR',
      internalCode: 'SAME_SKU',
      quantity: 20,
    });
    const result = consolidateCodeDetections([
      { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: b, symbology: 'QR_CODE', detectionIndex: 1 },
    ]);
    expect(result.productResults).toHaveLength(2);
    expect(result.productResults.map((p) => p.labelId).sort()).toEqual(
      ['A1B2C3D4E5', 'FGHJKMNPQR'].sort(),
    );
    expect(result.productResults.every((p) => p.labelId)).toBe(true);
    expect(result.productResults.every((p) => p.validationStatus === 'D1_VALID')).toBe(true);
  });

  it('mixed validity: valid D1s emit, invalid rejected, no photo-wide fail', () => {
    const a = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SKU_A',
      quantity: 1,
    });
    const b = buildProductLabelPayload({
      labelId: 'FGHJKMNPQR',
      internalCode: 'SKU_B',
      quantity: 2,
    });
    const vectors = JSON.parse(
      fs.readFileSync(
        path.resolve(__dirname, '../../contracts/product-labels/v1/checksum-vectors.json'),
        'utf8',
      ),
    ) as { vectors: Array<{ name: string; tampered_payload?: string }> };
    const tampered = vectors.vectors.find((v) => v.name === 'checksum-fail-tampered-qty')!;
    const result = consolidateCodeDetections([
      { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: b, symbology: 'QR_CODE', detectionIndex: 1 },
      {
        rawValue: tampered.tampered_payload as string,
        symbology: 'QR_CODE',
        detectionIndex: 2,
      },
    ]);
    expect(result.status).toBe('RESOLVED_MULTI');
    expect(result.productResults).toHaveLength(2);
    expect(result.rejections.length).toBeGreaterThanOrEqual(1);
    expect(result.warnings).toContain('D1_PARTIAL_REJECTIONS');
  });

  it('keeps positionRawPayload with products on same photo', () => {
    const a = buildProductLabelPayload({
      labelId: 'A1B2C3D4E5',
      internalCode: 'SKU100',
      quantity: 4,
    });
    const posRaw = JSON.stringify({
      type: 'DINAMIC_POSITION',
      version: 2,
      label_id: 'pos_co',
      pallet: '09',
      side: 'LEFT',
      level: 1,
      marker_index: 1,
      marker_total: 1,
    });
    const result = consolidateCodeDetections([
      { rawValue: a, symbology: 'QR_CODE', detectionIndex: 0 },
      { rawValue: posRaw, symbology: 'QR_CODE', detectionIndex: 1 },
    ]);
    expect(result.productResults).toHaveLength(1);
    expect(result.productResults[0]?.validationStatus).toBe('D1_VALID');
    expect(result.positionRawPayload).toBe(posRaw);
    expect(result.warnings).toContain('POSITION_LABEL_DETECTED');
  });
});
