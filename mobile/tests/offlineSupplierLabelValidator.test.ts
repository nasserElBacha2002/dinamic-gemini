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

  it('SEGMENTED: exact_length applies to label_id only (not full payload)', () => {
    const result = validateSupplierPayloadOffline({
      rawPayload: 'ASI-9T6R2V|48',
      labelKind: 'ITEM',
      configuration: {
        recognition_mode: 'FULL',
        required_fields: ['label_id', 'quantity'],
        quantity_rules: {
          required: true,
          expected_presence: 'ALWAYS',
          allow_external_fallback: false,
          minimum: 1,
        },
        deterministic: {
          expected_prefix: 'ASI',
          exact_length: 10,
          character_set: 'ALPHANUMERIC_WITH_HYPHEN',
          payload_structure: 'SEGMENTED',
          delimiter: '|',
          expected_segment_count: 2,
          field_mappings: [
            { target: 'label_id', source: 'SEGMENT', segment_index: 0 },
            { target: 'quantity', source: 'SEGMENT', segment_index: 1 },
          ],
          normalization: {
            case_normalization: 'UPPER',
            trim_outer_whitespace: true,
            remove_internal_spaces: true,
            remove_hyphens: false,
          },
        },
      },
      profileId: 'p-seg',
      profileVersion: 3,
    });
    expect(result.status).toBe('VALID');
    expect(result.errorCode).toBeNull();
    expect(result.labelId).toBe('ASI-9T6R2V');
    expect(result.quantity).toBe(48);
    expect(result.diagnostics.segment_count).toBe('2');
  });

  it('SEGMENTED: full payload length must not cause LABEL_LENGTH_MISMATCH', () => {
    const badId = validateSupplierPayloadOffline({
      rawPayload: 'ASI-9T6R2|48',
      labelKind: 'ITEM',
      configuration: {
        required_fields: ['label_id', 'quantity'],
        quantity_rules: { required: true, expected_presence: 'ALWAYS', minimum: 1 },
        deterministic: {
          expected_prefix: 'ASI',
          exact_length: 10,
          character_set: 'ALPHANUMERIC_WITH_HYPHEN',
          payload_structure: 'SEGMENTED',
          delimiter: '|',
          expected_segment_count: 2,
          field_mappings: [
            { target: 'label_id', source: 'SEGMENT', segment_index: 0 },
            { target: 'quantity', source: 'SEGMENT', segment_index: 1 },
          ],
        },
      },
      profileId: 'p',
      profileVersion: 1,
    });
    expect(badId.status).toBe('NOT_APPLICABLE');
    expect(badId.errorCode).toBe('LABEL_LENGTH_MISMATCH');
    expect((badId.diagnostics.length as { found: number }).found).toBe(9);
  });
});
