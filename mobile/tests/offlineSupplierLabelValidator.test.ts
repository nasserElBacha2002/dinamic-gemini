import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  validateSupplierPayloadOffline,
  type OfflineExtractionConfiguration,
} from '../src/core/offlineSupplierLabelValidator';

type VectorFile = {
  vectors: Array<{
    id: string;
    label_kind: 'ITEM' | 'POSITION';
    raw_payload: string;
    configuration: OfflineExtractionConfiguration;
    expected: {
      status: string;
      error_code?: string | null;
      label_id?: string | null;
      sku?: string | null;
      quantity?: number | null;
      position_id?: string | null;
    };
  }>;
};

const vectorsPath = resolve(
  __dirname,
  '../../contracts/offline-recognition/v1/minimal-vectors.json',
);

describe('offline supplier label validator — shared vectors', () => {
  const file = JSON.parse(readFileSync(vectorsPath, 'utf8')) as VectorFile;

  for (const vector of file.vectors) {
    it(vector.id, () => {
      const result = validateSupplierPayloadOffline({
        rawPayload: vector.raw_payload,
        labelKind: vector.label_kind,
        configuration: vector.configuration,
        profileId: 'profile-test',
        profileVersion: 3,
      });
      expect(result.status).toBe(vector.expected.status);
      if (vector.expected.error_code != null) {
        expect(result.errorCode).toBe(vector.expected.error_code);
      }
      if (vector.expected.label_id !== undefined) {
        expect(result.labelId).toBe(vector.expected.label_id);
      }
      if (vector.expected.sku !== undefined) {
        expect(result.sku).toBe(vector.expected.sku);
      }
      if (vector.expected.quantity !== undefined) {
        expect(result.quantity).toBe(vector.expected.quantity);
      }
      if (vector.expected.position_id !== undefined) {
        expect(result.positionId).toBe(vector.expected.position_id);
      }
      expect(result.profileVersion).toBe(3);
      expect(result.profileId).toBe('profile-test');
    });
  }

  it('never invents sku or quantity for MINIMAL identity', () => {
    const result = validateSupplierPayloadOffline({
      rawPayload: 'LPNA000184',
      labelKind: 'ITEM',
      configuration: {
        recognition_mode: 'MINIMAL',
        required_fields: ['label_id'],
        deterministic: {
          expected_prefix: 'LPNA',
          exact_length: 10,
          character_set: 'UPPERCASE_ALPHANUMERIC',
          payload_structure: 'SIMPLE',
          field_mappings: [{ target: 'label_id', source: 'WHOLE' }],
          normalization: { case_normalization: 'UPPER', trim_outer_whitespace: true },
        },
      },
      profileId: 'p',
      profileVersion: 1,
    });
    expect(result.status).toBe('VALID');
    expect(result.sku).toBeNull();
    expect(result.quantity).toBeNull();
  });
});
