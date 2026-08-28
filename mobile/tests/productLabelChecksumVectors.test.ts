import * as fs from 'fs';
import * as path from 'path';

import {
  buildProductLabelPayload,
  computeProductLabelChecksum,
  parseProductLabelPayload,
} from '../src/core/productLabelFormat';

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
    'utf8',
  ),
) as VectorsFile;

function vectorRaw(vec: VectorsFile['vectors'][number]): string | null {
  if ('raw' in vec) return vec.raw ?? null;
  if ('tampered_payload' in vec) return vec.tampered_payload ?? null;
  if ('payload' in vec) return vec.payload ?? null;
  return null;
}

describe('productLabelChecksumVectors (D1)', () => {
  it('matches shared checksum vectors for VALID fixtures', () => {
    for (const vec of vectors.vectors) {
      if (vec.expected_status !== 'VALID') continue;
      if (!vec.checksum || !vec.label_id) continue;
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

  it.each(
    vectors.vectors
      .filter((v) => vectorRaw(v) && v.expected_status)
      .map((v) => [v.name, vectorRaw(v)!, v.expected_status!] as const),
  )('parseProductLabelPayload(%s) → %s', (_name, raw, expected) => {
    expect(parseProductLabelPayload(raw).status).toBe(expected);
  });

  it('rejects external EAN as NOT_OUR_FORMAT', () => {
    expect(parseProductLabelPayload('7790001234567').status).toBe('NOT_OUR_FORMAT');
  });

  it('malformed D1| is MALFORMED not NOT_OUR_FORMAT', () => {
    expect(parseProductLabelPayload('D1|BAD|X|1|Z').status).toBe('MALFORMED');
  });
});
