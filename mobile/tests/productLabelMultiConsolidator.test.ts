import { consolidateCodeDetections } from '../src/core/codeDetectionConsolidator';
import { buildProductLabelPayload } from '../src/core/productLabelFormat';

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
});
