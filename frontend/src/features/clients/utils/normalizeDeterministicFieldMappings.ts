import type { ExtractionProfileConfiguration } from '../../../api/types/extractionProfile';

/**
 * Ensure SEGMENT mappings carry an explicit non-negative segment_index before save.
 * The editor historically displayed the list index as a fallback while leaving
 * ``segment_index`` null, which the API rejects.
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
      field_mappings: rules.field_mappings.map((mapping, index) => {
        if (mapping.source !== 'SEGMENT') {
          return { ...mapping, segment_index: null };
        }
        const raw = mapping.segment_index;
        const segment_index =
          typeof raw === 'number' && Number.isInteger(raw) && raw >= 0 ? raw : index;
        return { ...mapping, segment_index, application_identifier: null };
      }),
    },
  };
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

export function normalizeExtractionProfileForSave(
  configuration: ExtractionProfileConfiguration
): ExtractionProfileConfiguration {
  return normalizeQuantityRequiredConsistency(
    normalizeDeterministicFieldMappings(configuration)
  );
}
