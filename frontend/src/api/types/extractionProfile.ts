/**
 * Supplier extraction profile DTOs — aligned with backend Phase 6 schemas.
 */

export type ExtractionProfileStatus = 'DRAFT' | 'ACTIVE' | 'INACTIVE' | 'SUPERSEDED';

export type FieldDataType = 'TEXT' | 'INTEGER' | 'DECIMAL' | 'DATE' | 'CODE' | 'BOOLEAN';

export type SpatialRelation =
  | 'RIGHT_OF'
  | 'LEFT_OF'
  | 'ABOVE'
  | 'BELOW'
  | 'SAME_ROW'
  | 'SAME_COLUMN'
  | 'SAME_CELL'
  | 'NEAR'
  | 'INSIDE_REGION';

export interface InternalCodeSourceRule {
  field_key: string;
  priority: number;
  enabled: boolean;
  allowed_as_internal_code?: boolean;
  requires_label?: boolean;
  pattern?: string | null;
}

export interface QuantityExtractionRules {
  aliases: string[];
  required: boolean;
  data_type: FieldDataType | string;
  minimum: number;
  maximum: number;
  allow_decimals: boolean;
  allow_negative?: boolean;
  default_value?: number | null;
  accepted_units?: string[];
}

export interface AdditionalFieldRule {
  field_key: string;
  display_name: string;
  aliases: string[];
  data_type: FieldDataType | string;
  required: boolean;
  priority: number;
  normalization_rule?: string | null;
  validation_rule?: string | null;
}

export interface CodeValidationRules {
  min_length: number;
  max_length: number;
  allow_letters: boolean;
  allow_digits: boolean;
  allow_hyphen: boolean;
  allow_slash: boolean;
  allow_spaces: boolean;
  preserve_leading_zeros: boolean;
  regex?: string | null;
}

export interface EanValidationRules {
  allow_ean8: boolean;
  allow_ean12: boolean;
  allow_ean13: boolean;
  allow_ean14: boolean;
  validate_checksum: boolean;
}

export interface ExtractionValidationRules {
  code: CodeValidationRules;
  ean: EanValidationRules;
  quantity_integer_only: boolean;
}

export interface ExtractionProfileConfiguration {
  internal_code_sources: InternalCodeSourceRule[];
  forbidden_internal_code_sources?: string[];
  quantity_rules: QuantityExtractionRules;
  additional_fields: AdditionalFieldRule[];
  validation_rules: ExtractionValidationRules;
  accepted_barcode_formats: string[];
  qr_payload_formats?: string[];
  custom_payload_pattern?: string | null;
  required_fields?: string[];
  aliases?: Record<string, string[]>;
}

export interface SupplierExtractionProfile {
  id: string;
  client_id: string;
  supplier_id: string;
  profile_key: string;
  version: number;
  status: ExtractionProfileStatus | string;
  configuration: ExtractionProfileConfiguration;
  visual_notes: string | null;
  created_by: string | null;
  created_at: string;
  activated_by: string | null;
  activated_at: string | null;
  superseded_at: string | null;
  updated_at: string | null;
  row_version: number;
}

export interface SupplierExtractionProfilesListResponse {
  items: SupplierExtractionProfile[];
}

export interface ReferenceAnnotation {
  id: string;
  template_image_id: string;
  profile_id: string | null;
  field_key: string;
  anchor_texts: string[];
  spatial_relation: SpatialRelation | string;
  normalized_polygon: number[][] | null;
  priority: number;
  required: boolean;
  max_distance_ratio: number | null;
}

export interface SupplierReferenceAnnotationsListResponse {
  items: ReferenceAnnotation[];
}

export interface ReferenceAnnotationPayload {
  id?: string | null;
  field_key: string;
  anchor_texts: string[];
  spatial_relation: SpatialRelation | string;
  normalized_polygon?: number[][] | null;
  priority?: number;
  required?: boolean;
  max_distance_ratio?: number | null;
}
