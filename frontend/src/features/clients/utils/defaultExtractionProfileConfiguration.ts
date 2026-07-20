import type { ExtractionProfileConfiguration } from '../../../api/types/extractionProfile';

/** Mirrors backend ``default_extraction_configuration()`` for empty-state editing. */
export function defaultExtractionProfileConfiguration(): ExtractionProfileConfiguration {
  return {
    internal_code_sources: [
      { field_key: 'INTERNAL_CODE', priority: 1, enabled: true },
      { field_key: 'EAN', priority: 2, enabled: true },
      { field_key: 'ARTICLE', priority: 3, enabled: true },
    ],
    forbidden_internal_code_sources: [],
    quantity_rules: {
      aliases: ['CANTIDAD', 'CANT.', 'QTY', 'QUANTITY', 'UNIDADES'],
      required: true,
      data_type: 'INTEGER',
      minimum: 1,
      maximum: 99_999_999,
      allow_decimals: false,
      allow_negative: false,
      default_value: null,
      accepted_units: [],
    },
    additional_fields: [],
    validation_rules: {
      code: {
        min_length: 1,
        max_length: 128,
        allow_letters: true,
        allow_digits: true,
        allow_hyphen: true,
        allow_slash: true,
        allow_spaces: false,
        preserve_leading_zeros: true,
        regex: null,
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
    accepted_barcode_formats: ['QR', 'CODE128', 'EAN13', 'EAN8', 'UPC_A'],
    qr_payload_formats: ['PLAIN_CODE', 'CODE_QUANTITY_PIPE', 'DI1', 'LABELED'],
    custom_payload_pattern: null,
    required_fields: ['internal_code', 'quantity'],
    aliases: {
      internal_code: ['CÓDIGO INTERNO', 'CODIGO INTERNO', 'CÓD.', 'COD', 'SKU', 'INTERNAL_CODE'],
      ean: ['EAN', 'EAN13', 'CÓDIGO EAN', 'CODIGO EAN'],
      article: ['ARTÍCULO', 'ARTICULO', 'ARTICLE'],
      quantity: ['CANTIDAD', 'CANT.', 'QTY', 'QUANTITY', 'UNIDADES'],
    },
  };
}

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
