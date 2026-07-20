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

export type LabelBackgroundHint = 'LIGHT' | 'DARK' | 'VARIABLE' | 'DISABLED';
export type LabelShapeHint = 'RECTANGULAR' | 'APPROXIMATELY_RECTANGULAR' | 'VARIABLE';
export type LabelOrientationHint = 'HORIZONTAL' | 'VERTICAL' | 'SQUARE_OR_VERTICAL' | 'ANY';
export type QuantityPresence = 'ALWAYS' | 'OPTIONAL' | 'UNKNOWN';
export type MissingQuantityAction =
  | 'PENDING_MANUAL_REVIEW'
  | 'EXTERNAL_FALLBACK'
  | 'UNRECOGNIZED'
  | 'RESOLVE_CODE_ONLY';

export interface InternalCodeSourceRule {
  field_key: string;
  priority: number;
  enabled: boolean;
  allowed_as_internal_code?: boolean;
  requires_label?: boolean;
  pattern?: string | null;
  aliases?: string[];
  allowed_spatial_relations?: string[];
  maximum_anchor_distance_ratio?: number | null;
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
  expected_presence?: QuantityPresence | string;
  missing_quantity_action?: MissingQuantityAction | string;
  allow_external_fallback?: boolean;
  allowed_spatial_relations?: string[];
  maximum_anchor_distance_ratio?: number | null;
}

export interface LabelDetectionRules {
  enabled?: boolean;
  expected_background?: LabelBackgroundHint | string;
  expected_shape?: LabelShapeHint | string;
  expected_orientation?: LabelOrientationHint | string;
  primary_anchors?: string[];
  secondary_anchors?: string[];
  minimum_anchor_matches?: number;
  minimum_relative_area?: number;
  maximum_relative_area?: number;
  allow_rotation?: boolean;
  allow_perspective_correction?: boolean;
  allow_full_image_fallback?: boolean;
  maximum_candidate_regions?: number;
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
  exact_length?: number | null;
  allow_letters: boolean;
  allow_digits: boolean;
  allow_hyphen: boolean;
  allow_slash: boolean;
  allow_spaces: boolean;
  preserve_leading_zeros: boolean;
  regex?: string | null;
  reject_measurement_patterns?: boolean;
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
  label_detection_rules?: LabelDetectionRules;
  accepted_barcode_formats: string[];
  qr_payload_formats?: string[];
  custom_payload_pattern?: string | null;
  required_fields?: string[];
  aliases?: Record<string, string[]>;
  allow_unconfigured_code_source_fallback?: boolean;
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
