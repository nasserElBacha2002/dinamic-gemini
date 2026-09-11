import { describe, expect, it } from 'vitest';
import {
  normalizeDeterministicFieldMappings,
  validateDeterministicFieldMappings,
  validateExtractionProfileForSave,
} from '../src/features/clients/utils/normalizeDeterministicFieldMappings';
import { defaultExtractionProfileConfiguration } from '../src/features/clients/utils/defaultExtractionProfileConfiguration';

function segmentedConfig() {
  const configuration = defaultExtractionProfileConfiguration('ITEM');
  return {
    ...configuration,
    deterministic: {
      ...configuration.deterministic!,
      payload_structure: 'SEGMENTED' as const,
      delimiter: '|',
      expected_segment_count: 3,
      field_mappings: [
        { target: 'label_id', source: 'SEGMENT' as const, segment_index: 2, application_identifier: null },
        { target: 'sku', source: 'SEGMENT' as const, segment_index: 0, application_identifier: null },
        { target: 'quantity', source: 'SEGMENT' as const, segment_index: 1, application_identifier: null },
      ],
    },
  };
}

describe('normalizeDeterministicFieldMappings', () => {
  it('does not invent segment_index from row order', () => {
    const configuration = segmentedConfig();
    configuration.deterministic!.field_mappings[0].segment_index = null;
    const normalized = normalizeDeterministicFieldMappings(configuration);
    expect(normalized.deterministic?.field_mappings[0].segment_index).toBeNull();
    expect(normalized.deterministic?.field_mappings[1].segment_index).toBe(0);
  });

  it('keeps explicit indexes when rows are reordered', () => {
    const normalized = normalizeDeterministicFieldMappings(segmentedConfig());
    expect(normalized.deterministic?.field_mappings.map((row) => row.segment_index)).toEqual([2, 0, 1]);
  });

  it('blocks missing, invalid, duplicate-range, and out-of-range indexes', () => {
    const missing = segmentedConfig();
    missing.deterministic!.field_mappings[0].segment_index = null;
    expect(validateDeterministicFieldMappings(missing).some((issue) => issue.code === 'SEGMENT_INDEX_REQUIRED')).toBe(true);

    const invalid = segmentedConfig();
    invalid.deterministic!.field_mappings[0].segment_index = -1;
    expect(validateDeterministicFieldMappings(invalid).some((issue) => issue.code === 'SEGMENT_INDEX_INVALID')).toBe(true);

    const outOfRange = segmentedConfig();
    outOfRange.deterministic!.field_mappings[0].segment_index = 9;
    expect(validateDeterministicFieldMappings(outOfRange).some((issue) => issue.code === 'SEGMENT_INDEX_OUT_OF_RANGE')).toBe(true);

    const duplicateTargets = segmentedConfig();
    expect(validateDeterministicFieldMappings(duplicateTargets)).toEqual([]);
  });

  it('rejects allow_decimals=true on save', () => {
    const configuration = segmentedConfig();
    configuration.quantity_rules.allow_decimals = true;
    expect(validateExtractionProfileForSave(configuration)).toContain('QUANTITY_DECIMALS_NOT_SUPPORTED');
  });
});
