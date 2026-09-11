import type { ExtractionProfileConfiguration } from '../../../api/types/extractionProfile';

export type FieldMappingValidationIssue = {
  index: number;
  code: 'SEGMENT_INDEX_REQUIRED' | 'SEGMENT_INDEX_INVALID' | 'SEGMENT_INDEX_OUT_OF_RANGE';
};

function isExplicitNonNegativeInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

/**
 * SEGMENT mappings must carry an explicit non-negative segment_index.
 * Do not invent an index from the row order during save.
 */
export function normalizeDeterministicFieldMappings(
  configuration: ExtractionProfileConfiguration
): ExtractionProfileConfiguration {
  const rules = configuration.deterministic;
  if (!rules) return configuration;
  return {
    ...configuration,
    deterministic: {
      ...rules,
      field_mappings: rules.field_mappings.map((mapping) => {
        if (mapping.source !== 'SEGMENT') {
          return { ...mapping, segment_index: null };
        }
        return { ...mapping, application_identifier: null };
      }),
    },
  };
}

export function validateDeterministicFieldMappings(
  configuration: ExtractionProfileConfiguration
): FieldMappingValidationIssue[] {
  const rules = configuration.deterministic;
  if (!rules) return [];
  const expectedCount = rules.expected_segment_count;
  const issues: FieldMappingValidationIssue[] = [];
  rules.field_mappings.forEach((mapping, index) => {
    if (mapping.source !== 'SEGMENT') return;
    const raw = mapping.segment_index;
    if (!isExplicitNonNegativeInt(raw)) {
      issues.push({
        index,
        code: raw == null ? 'SEGMENT_INDEX_REQUIRED' : 'SEGMENT_INDEX_INVALID',
      });
      return;
    }
    if (typeof expectedCount === 'number' && expectedCount > 0 && raw >= expectedCount) {
      issues.push({ index, code: 'SEGMENT_INDEX_OUT_OF_RANGE' });
    }
  });
  return issues;
}

/**
 * Keep quantity_rules.required / expected_presence / required_fields coherent.
 * Backend rejects contradictory combinations at activate/save.
 */
export function normalizeQuantityRequiredConsistency(
  configuration: ExtractionProfileConfiguration
): ExtractionProfileConfiguration {
  const qtyRules = configuration.quantity_rules;
  const requiredFields = [...(configuration.required_fields ?? [])];
  const hasQuantityField = requiredFields.includes('quantity');
  const required =
    Boolean(qtyRules.required) ||
    hasQuantityField ||
    qtyRules.expected_presence === 'ALWAYS';

  const nextFields = requiredFields.filter((field) => field !== 'quantity');
  if (required) {
    nextFields.push('quantity');
  }

  return {
    ...configuration,
    required_fields: nextFields,
    quantity_rules: {
      ...qtyRules,
      required,
      expected_presence: required
        ? 'ALWAYS'
        : qtyRules.expected_presence === 'ALWAYS'
          ? 'OPTIONAL'
          : qtyRules.expected_presence,
    },
  };
}

export function validateExtractionProfileForSave(
  configuration: ExtractionProfileConfiguration
): string[] {
  const errors: string[] = [];
  if (configuration.quantity_rules?.allow_decimals) {
    errors.push('QUANTITY_DECIMALS_NOT_SUPPORTED');
  }
  const mappingIssues = validateDeterministicFieldMappings(configuration);
  for (const issue of mappingIssues) {
    errors.push(`${issue.code}:${issue.index}`);
  }
  return errors;
}

export function normalizeExtractionProfileForSave(
  configuration: ExtractionProfileConfiguration
): ExtractionProfileConfiguration {
  return normalizeQuantityRequiredConsistency(
    normalizeDeterministicFieldMappings(configuration)
  );
}
