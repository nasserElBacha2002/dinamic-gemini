import * as fs from 'fs';
import * as path from 'path';
import { describe, expect, it } from 'vitest';
import {
  buildProductLabelPayload,
  computeProductLabelChecksum,
  parseProductLabelPayload,
} from '../src/features/clients/components/productLabelPayload';

type VectorsFile = {
  vectors: Array<{
    name: string;
    label_id?: string;
    internal_code?: string;
    quantity?: number;
    checksum?: string;
    payload?: string;
    tampered_payload?: string;
    expected_status?: string;
    raw?: string;
  }>;
};

const vectors = JSON.parse(
  fs.readFileSync(
    path.resolve(__dirname, '../../contracts/product-labels/v1/checksum-vectors.json'),
    'utf8'
  )
) as VectorsFile;

describe('productLabelPayload D1', () => {
  it('matches shared checksum vectors', () => {
    for (const vec of vectors.vectors) {
      if (!vec.checksum || !vec.label_id || vec.expected_status) continue;
      const cs = computeProductLabelChecksum({
        labelId: vec.label_id,
        internalCode: vec.internal_code as string,
        quantity: vec.quantity as number,
      });
      expect(cs).toBe(vec.checksum);
      const payload = buildProductLabelPayload({
        labelId: vec.label_id,
        internalCode: vec.internal_code as string,
        quantity: vec.quantity as number,
      });
      expect(payload).toBe(vec.payload);
      expect(parseProductLabelPayload(payload).status).toBe('VALID');
    }
  });

  it('rejects tampered checksum', () => {
    const vec = vectors.vectors.find((v) => v.name === 'checksum-fail-tampered-qty')!;
    expect(parseProductLabelPayload(vec.tampered_payload as string).status).toBe(
      'CHECKSUM_FAILED'
    );
  });

  it('rejects external EAN', () => {
    expect(parseProductLabelPayload('7790001234567').status).toBe('NOT_OUR_FORMAT');
  });
});
