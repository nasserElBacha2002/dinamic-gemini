import type { ExtractionProfileConfiguration, LabelKind } from '../../../api/types/extractionProfile';

/** Minimal SUPPLIER v2 default — identity first (prefix/length/charset + primary target). */
export function defaultExtractionProfileConfiguration(
  labelKind: LabelKind = 'ITEM'
): ExtractionProfileConfiguration {
  const isPosition = labelKind === 'POSITION';
  return {
    configuration_schema_version: 2,
    recognition_mode: 'MINIMAL',
    semantic_type: isPosition ? 'LOCATION' : 'LPN',
    deterministic: {
      expected_prefix: null,
      expected_suffix: null,
      exact_length: null,
      min_length: null,
      max_length: null,
      character_set: isPosition ? 'ALPHANUMERIC_WITH_HYPHEN' : 'UPPERCASE_ALPHANUMERIC',
      normalization: {
        trim_outer_whitespace: true,
        case_normalization: 'UPPER',
        remove_internal_spaces: true,
        remove_hyphens: false,
      },
      payload_structure: 'SIMPLE',
      delimiter: null,
      expected_segment_count: null,
      field_mappings: [
        { target: isPosition ? 'position_id' : 'label_id', source: 'WHOLE' },
      ],
      checksum_policy: 'NONE',
      required_application_identifiers: [],
      optional_application_identifiers: [],
      use_advanced_pattern: false,
    },
    valid_examples: [],
    invalid_examples: [],
    internal_code_sources: [],
    forbidden_internal_code_sources: [],
    quantity_rules: {
      aliases: [],
      required: false,
      data_type: 'INTEGER',
      minimum: 1,
      maximum: 99_999_999,
      allow_decimals: false,
      allow_negative: false,
      default_value: null,
      accepted_units: [],
      expected_presence: 'OPTIONAL',
      missing_quantity_action: 'PENDING_MANUAL_REVIEW',
      allow_external_fallback: false,
      allowed_spatial_relations: [],
    },
    label_detection_rules: {
      enabled: true,
      expected_background: 'VARIABLE',
      expected_shape: 'APPROXIMATELY_RECTANGULAR',
      expected_orientation: 'ANY',
      primary_anchors: [],
      secondary_anchors: [],
      minimum_anchor_matches: 0,
      minimum_relative_area: 0.005,
      maximum_relative_area: 0.45,
      allow_rotation: true,
      allow_perspective_correction: true,
      allow_full_image_fallback: true,
      maximum_candidate_regions: 8,
      approx_width_mm: null,
      approx_height_mm: null,
      size_tolerance_percent: null,
    },
    additional_fields: [],
    validation_rules: {
      code: {
        min_length: 1,
        max_length: 128,
        exact_length: null,
        allow_letters: true,
        allow_digits: true,
        allow_hyphen: true,
        allow_slash: false,
        allow_spaces: false,
        preserve_leading_zeros: true,
        regex: null,
        reject_measurement_patterns: false,
      },
      ean: {
        allow_ean8: true,
        allow_ean12: true,
        allow_ean13: true,
        allow_ean14: true,
        validate_checksum: true,
      },
      quantity_integer_only: true,
    },
    accepted_barcode_formats: ['QR', 'CODE128'],
    qr_payload_formats: ['PLAIN_CODE'],
    custom_payload_pattern: null,
    required_fields: [isPosition ? 'position_id' : 'label_id'],
    aliases: {},
  };
}

export function gs1SsccTemplate(): ExtractionProfileConfiguration {
  const base = defaultExtractionProfileConfiguration('ITEM');
  return {
    ...base,
    recognition_mode: 'FULL',
    semantic_type: 'SSCC',
    required_fields: ['label_id'],
    deterministic: {
      ...base.deterministic!,
      payload_structure: 'GS1',
      character_set: 'NUMERIC',
      exact_length: 20,
      min_length: 20,
      max_length: 20,
      field_mappings: [
        { target: 'label_id', source: 'APPLICATION_IDENTIFIER', application_identifier: '00' },
      ],
      required_application_identifiers: ['00'],
      checksum_policy: 'EAN_GTIN',
    },
  };
}

export function gs1GtinTemplate(): ExtractionProfileConfiguration {
  const base = defaultExtractionProfileConfiguration('ITEM');
  return {
    ...base,
    recognition_mode: 'FULL',
    semantic_type: 'PRODUCT_SKU',
    required_fields: ['sku'],
    quantity_rules: { ...base.quantity_rules, required: false },
    deterministic: {
      ...base.deterministic!,
      payload_structure: 'GS1',
      character_set: 'NUMERIC',
      field_mappings: [
        { target: 'sku', source: 'APPLICATION_IDENTIFIER', application_identifier: '01' },
      ],
      required_application_identifiers: ['01'],
      optional_application_identifiers: ['10', '17', '21', '37'],
      checksum_policy: 'EAN_GTIN',
    },
  };
}

export function lpnSimpleTemplate(): ExtractionProfileConfiguration {
  const base = defaultExtractionProfileConfiguration('ITEM');
  return {
    ...base,
    recognition_mode: 'MINIMAL',
    semantic_type: 'LPN',
    required_fields: ['label_id'],
    deterministic: {
      ...base.deterministic!,
      payload_structure: 'SIMPLE',
      character_set: 'UPPERCASE_ALPHANUMERIC',
      normalization: {
        ...base.deterministic!.normalization,
        case_normalization: 'UPPER',
      },
      field_mappings: [{ target: 'label_id', source: 'WHOLE' }],
    },
  };
}

export const LABEL_RECOGNITION_TEMPLATES = [
  { id: 'gs1_sscc', labelKey: 'clients.extraction_profile.template_gs1_sscc', build: gs1SsccTemplate },
  { id: 'gs1_gtin', labelKey: 'clients.extraction_profile.template_gs1_gtin', build: gs1GtinTemplate },
  { id: 'lpn_simple', labelKey: 'clients.extraction_profile.template_lpn_simple', build: lpnSimpleTemplate },
] as const;

/** Opt-in template — never auto-applied. */
export function inventorySevenDigitInternalCodeTemplate(): ExtractionProfileConfiguration {
  const base = defaultExtractionProfileConfiguration('ITEM');
  return {
    ...base,
    recognition_mode: 'FULL',
    configuration_schema_version: 1,
    semantic_type: 'CUSTOM',
    required_fields: ['internal_code', 'quantity'],
    internal_code_sources: [
      {
        field_key: 'INTERNAL_CODE',
        priority: 1,
        enabled: true,
        aliases: ['CÓDIGO INTERNO', 'CODIGO INTERNO', 'COD. INTERNO'],
        allowed_spatial_relations: ['BELOW', 'SAME_COLUMN', 'NEAR'],
      },
      { field_key: 'EAN', priority: 2, enabled: false },
      { field_key: 'ARTICLE', priority: 3, enabled: false },
    ],
    quantity_rules: {
      ...base.quantity_rules,
      required: true,
      expected_presence: 'ALWAYS',
      aliases: ['CANT. TOTAL', 'CANTIDAD', 'CANT.', 'QTY', 'QUANTITY', 'UNIDADES'],
    },
    label_detection_rules: {
      enabled: true,
      expected_background: 'LIGHT',
      expected_shape: 'APPROXIMATELY_RECTANGULAR',
      expected_orientation: 'ANY',
      primary_anchors: ['CÓDIGO INTERNO', 'CODIGO INTERNO', 'COD. INTERNO'],
      secondary_anchors: ['INVENTARIO GENERAL', 'CANT. TOTAL', 'CANTIDAD'],
      minimum_anchor_matches: 1,
      anchor_match_policy: 'ANCHORS_PREFERRED',
      minimum_relative_area: 0.005,
      maximum_relative_area: 0.45,
      allow_rotation: true,
      allow_perspective_correction: true,
      allow_full_image_fallback: true,
      maximum_candidate_regions: 8,
    },
    validation_rules: {
      ...base.validation_rules,
      code: {
        ...base.validation_rules.code,
        exact_length: 7,
        min_length: 7,
        max_length: 7,
        allow_letters: false,
        allow_digits: true,
        allow_hyphen: false,
        allow_slash: false,
        reject_measurement_patterns: true,
        unanchored_candidate_policy: 'ALLOW_FOR_MANUAL_REVIEW',
      },
    },
    aliases: {
      quantity: ['CANT. TOTAL', 'CANTIDAD', 'CANT.', 'QTY', 'QUANTITY', 'UNIDADES'],
    },
  };
}

export const EXTRACTION_PROFILE_TEMPLATES = [
  {
    id: 'conservative_default',
    labelKey: 'clients.extraction_profile.template_conservative',
    build: () => defaultExtractionProfileConfiguration('ITEM'),
  },
  {
    id: 'inventory_7_digit',
    labelKey: 'clients.extraction_profile.template_inventory_7_digit',
    build: inventorySevenDigitInternalCodeTemplate,
  },
] as const;

export const INTERNAL_CODE_SOURCE_KEYS = ['EAN', 'INTERNAL_CODE', 'ARTICLE', 'SKU', 'PRODUCT'] as const;

export const SUPPORTED_BARCODE_FORMATS = [
  'QR',
  'CODE128',
  'EAN8',
  'EAN13',
  'UPC_A',
  'CODE39',
  'I25',
  'PDF417',
  'DATABAR',
] as const;

export const SPATIAL_RELATIONS = [
  'RIGHT_OF',
  'LEFT_OF',
  'ABOVE',
  'BELOW',
  'SAME_ROW',
  'SAME_COLUMN',
  'SAME_CELL',
  'NEAR',
  'INSIDE_REGION',
] as const;

export const INTERNAL_CODE_SOURCE_LABELS: Record<string, string> = {
  INTERNAL_CODE: 'Código interno',
  EAN: 'EAN',
  ARTICLE: 'Artículo',
  SKU: 'SKU',
  PRODUCT: 'Producto',
};

export const BASIC_CHARSET_OPTIONS = [
  { value: 'NUMERIC', labelKey: 'clients.extraction_profile.charset_numeric' },
  { value: 'ALPHANUMERIC', labelKey: 'clients.extraction_profile.charset_alphanumeric' },
  { value: 'UPPERCASE_ALPHANUMERIC', labelKey: 'clients.extraction_profile.charset_uppercase_alphanumeric' },
  { value: 'ALPHANUMERIC_WITH_HYPHEN', labelKey: 'clients.extraction_profile.charset_with_hyphen' },
  { value: 'ANY', labelKey: 'clients.extraction_profile.charset_any' },
] as const;
