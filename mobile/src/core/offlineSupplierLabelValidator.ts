/**
 * Offline supplier label recognition — deterministic subset mirroring backend
 * LabelValidationService (MINIMAL / SIMPLE / SEGMENTED).
 * GS1 is intentionally NOT implemented in this phase.
 */

export type LocalRecognitionStatus =
  | 'VALID'
  | 'INVALID'
  | 'NOT_APPLICABLE'
  | 'UNRESOLVED_OFFLINE'
  | 'PROFILE_MISSING'
  | 'AMBIGUOUS_LABEL_KIND'
  | 'TECHNICAL_ERROR';

export type CharacterSetPolicy =
  | 'NUMERIC'
  | 'ALPHANUMERIC'
  | 'UPPERCASE_ALPHANUMERIC'
  | 'ALPHANUMERIC_WITH_HYPHEN'
  | 'HEX'
  | 'ANY';

export type PayloadStructure = 'SIMPLE' | 'SEGMENTED' | 'GS1';

export interface OfflineDeterministicRules {
  expected_prefix?: string | null;
  expected_suffix?: string | null;
  exact_length?: number | null;
  min_length?: number | null;
  max_length?: number | null;
  character_set?: CharacterSetPolicy | string | null;
  normalization?: {
    trim_outer_whitespace?: boolean;
    case_normalization?: 'NONE' | 'UPPER' | 'LOWER' | string;
    remove_internal_spaces?: boolean;
    remove_hyphens?: boolean;
  } | null;
  payload_structure?: PayloadStructure | string | null;
  delimiter?: string | null;
  expected_segment_count?: number | null;
  field_mappings?: ReadonlyArray<{
    target: string;
    source: 'WHOLE' | 'SEGMENT' | 'APPLICATION_IDENTIFIER' | string;
    segment_index?: number | null;
  }>;
  use_advanced_pattern?: boolean;
}

export interface OfflineExtractionConfiguration {
  configuration_schema_version?: number;
  recognition_mode?: string | null;
  semantic_type?: string | null;
  deterministic?: OfflineDeterministicRules | null;
  required_fields?: string[];
  quantity_rules?: { required?: boolean } | null;
  custom_payload_pattern?: string | null;
}

export interface LocalRecognitionResult {
  readonly status: LocalRecognitionStatus;
  readonly errorCode: string | null;
  readonly detail: string | null;
  readonly labelKind: 'ITEM' | 'POSITION' | null;
  readonly rawPayload: string;
  readonly normalizedPayload: string | null;
  readonly labelId: string | null;
  readonly sku: string | null;
  readonly quantity: number | null;
  readonly positionId: string | null;
  readonly pallet: string | null;
  readonly side: string | null;
  readonly level: string | null;
  readonly diagnostics: Record<string, unknown>;
  readonly profileSource: 'DINAMIC' | 'SUPPLIER' | null;
  readonly profileId: string | null;
  readonly profileVersion: number | null;
  readonly configurationSchemaVersion: number | null;
}

function emptyResult(
  raw: string,
  patch: Partial<LocalRecognitionResult> & Pick<LocalRecognitionResult, 'status'>,
): LocalRecognitionResult {
  return {
    errorCode: null,
    detail: null,
    labelKind: null,
    rawPayload: raw,
    normalizedPayload: null,
    labelId: null,
    sku: null,
    quantity: null,
    positionId: null,
    pallet: null,
    side: null,
    level: null,
    diagnostics: {},
    profileSource: null,
    profileId: null,
    profileVersion: numberOrNull(null),
    configurationSchemaVersion: null,
    ...patch,
  };
}

function numberOrNull(v: number | null | undefined): number | null {
  return v == null ? null : v;
}

/** Same order as backend LabelValidationService / StructuredPayloadExtractor. */
export function normalizeOfflinePayload(
  raw: string,
  rules: OfflineDeterministicRules | null | undefined,
): string {
  let value = raw ?? '';
  const norm = rules?.normalization ?? {};
  if (norm.trim_outer_whitespace !== false) {
    value = value.trim();
  }
  const caseMode = String(norm.case_normalization ?? 'NONE').toUpperCase();
  if (caseMode === 'UPPER') value = value.toUpperCase();
  if (caseMode === 'LOWER') value = value.toLowerCase();
  if (norm.remove_internal_spaces) value = value.replace(/\s+/g, '');
  if (norm.remove_hyphens) value = value.replace(/-/g, '');
  return value;
}

function charsetOk(normalized: string, charset: string | null | undefined): boolean {
  const c = String(charset ?? 'ANY').toUpperCase();
  if (c === 'ANY') return true;
  if (c === 'NUMERIC') return /^\d+$/.test(normalized);
  if (c === 'HEX') return /^[0-9a-fA-F]+$/.test(normalized);
  if (c === 'UPPERCASE_ALPHANUMERIC') {
    return /^[A-Z0-9]+$/.test(normalized) && normalized === normalized.toUpperCase();
  }
  if (c === 'ALPHANUMERIC') return /^[A-Za-z0-9]+$/.test(normalized);
  if (c === 'ALPHANUMERIC_WITH_HYPHEN') return /^[A-Za-z0-9-]+$/.test(normalized);
  return true;
}

function extractFields(
  normalized: string,
  rules: OfflineDeterministicRules,
  labelKind: 'ITEM' | 'POSITION',
): Record<string, string | number | null> {
  const structure = String(rules.payload_structure ?? 'SIMPLE').toUpperCase();
  const mappings = rules.field_mappings ?? [];
  const out: Record<string, string | number | null> = {};

  if (structure === 'GS1') {
    throw new Error('GS1_NOT_SUPPORTED_OFFLINE');
  }

  if (structure === 'SEGMENTED') {
    const delimiter = rules.delimiter ?? '|';
    const parts = normalized.split(delimiter);
    if (
      rules.expected_segment_count != null &&
      parts.length !== Number(rules.expected_segment_count)
    ) {
      throw Object.assign(new Error('SEGMENT_COUNT_MISMATCH'), {
        code: 'LABEL_SEGMENT_COUNT_MISMATCH',
      });
    }
    for (const mapping of mappings) {
      if (String(mapping.source).toUpperCase() !== 'SEGMENT') continue;
      const idx = mapping.segment_index;
      if (idx == null || idx < 0 || idx >= parts.length) continue;
      const target = String(mapping.target).toLowerCase();
      const value = parts[idx] ?? '';
      if (target === 'quantity') {
        const n = Number.parseInt(value, 10);
        out.quantity = Number.isFinite(n) ? n : null;
      } else {
        out[target] = value;
      }
    }
    return out;
  }

  // SIMPLE
  for (const mapping of mappings) {
    if (String(mapping.source).toUpperCase() !== 'WHOLE') continue;
    const target = String(mapping.target).toLowerCase();
    if (target === 'quantity') {
      const n = Number.parseInt(normalized, 10);
      out.quantity = Number.isFinite(n) ? n : null;
    } else {
      out[target] = normalized;
    }
  }
  if (mappings.length === 0) {
    if (labelKind === 'POSITION') out.position_id = normalized;
    else out.label_id = normalized;
  }
  return out;
}

export function validateSupplierPayloadOffline(input: {
  rawPayload: string;
  labelKind: 'ITEM' | 'POSITION';
  configuration: OfflineExtractionConfiguration;
  profileId: string;
  profileVersion: number;
}): LocalRecognitionResult {
  const raw = input.rawPayload ?? '';
  const cfg = input.configuration;
  const rules = cfg.deterministic ?? {};
  const structure = String(rules.payload_structure ?? 'SIMPLE').toUpperCase();
  if (structure === 'GS1') {
    return emptyResult(raw, {
      status: 'UNRESOLVED_OFFLINE',
      errorCode: 'GS1_NOT_SUPPORTED_OFFLINE',
      detail: 'GS1 offline validation is not implemented in this phase',
      labelKind: input.labelKind,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  const normalized = normalizeOfflinePayload(raw, rules);
  const diagnostics: Record<string, unknown> = {
    found: normalized,
    prefix: {
      expected: rules.expected_prefix ?? null,
      pass: true,
    },
    length: {
      found: normalized.length,
      exact_expected: rules.exact_length ?? null,
      min: rules.min_length ?? null,
      max: rules.max_length ?? null,
      pass: true,
    },
    charset: {
      expected: rules.character_set ?? 'ANY',
      pass: true,
    },
  };

  const prefix = (rules.expected_prefix || '').trim();
  if (prefix && !normalized.startsWith(prefix)) {
    (diagnostics.prefix as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_PREFIX_MISMATCH',
      detail: `PREFIX_MISMATCH: expected ${prefix}`,
      labelKind: input.labelKind,
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }
  const suffix = (rules.expected_suffix || '').trim();
  if (suffix && !normalized.endsWith(suffix)) {
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_SUFFIX_MISMATCH',
      detail: `suffix mismatch`,
      labelKind: input.labelKind,
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  const length = normalized.length;
  if (rules.exact_length != null && length !== Number(rules.exact_length)) {
    (diagnostics.length as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_LENGTH_MISMATCH',
      detail: `LENGTH_MISMATCH: expected ${rules.exact_length}, found ${length}`,
      labelKind: input.labelKind,
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }
  if (rules.min_length != null && length < Number(rules.min_length)) {
    (diagnostics.length as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_LENGTH_MISMATCH',
      detail: `min_length`,
      labelKind: input.labelKind,
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }
  if (rules.max_length != null && length > Number(rules.max_length)) {
    (diagnostics.length as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_LENGTH_MISMATCH',
      detail: `max_length`,
      labelKind: input.labelKind,
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  if (!charsetOk(normalized, rules.character_set ?? null)) {
    (diagnostics.charset as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_CHARSET_MISMATCH',
      detail: 'CHARSET_MISMATCH',
      labelKind: input.labelKind,
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  let fields: Record<string, string | number | null>;
  try {
    fields = extractFields(normalized, rules, input.labelKind);
  } catch (e) {
    const code = (e as { code?: string }).code ?? 'TECHNICAL_ERROR';
    return emptyResult(raw, {
      status: code === 'LABEL_SEGMENT_COUNT_MISMATCH' ? 'NOT_APPLICABLE' : 'TECHNICAL_ERROR',
      errorCode: code,
      detail: e instanceof Error ? e.message : 'extract failed',
      labelKind: input.labelKind,
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  const required = new Set(
    (cfg.required_fields ?? []).map((f) => String(f).trim().toLowerCase()),
  );
  const isMinimal = String(cfg.recognition_mode ?? '').toUpperCase() === 'MINIMAL';
  if (input.labelKind === 'ITEM') {
    const labelId = (fields.label_id as string | null) ?? null;
    const sku = (fields.sku as string | null) || (fields.internal_code as string | null) || null;
    let quantity: number | null =
      typeof fields.quantity === 'number' ? fields.quantity : null;
    if (required.has('label_id') && !labelId) {
      return emptyResult(raw, {
        status: 'INVALID',
        errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
        detail: 'label_id required',
        labelKind: 'ITEM',
        normalizedPayload: normalized,
        diagnostics,
        profileSource: 'SUPPLIER',
        profileId: input.profileId,
        profileVersion: input.profileVersion,
        configurationSchemaVersion: cfg.configuration_schema_version ?? null,
      });
    }
    if ((required.has('sku') || required.has('internal_code')) && !sku) {
      return emptyResult(raw, {
        status: 'INVALID',
        errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
        detail: 'sku required',
        labelKind: 'ITEM',
        normalizedPayload: normalized,
        diagnostics,
        profileSource: 'SUPPLIER',
        profileId: input.profileId,
        profileVersion: input.profileVersion,
        configurationSchemaVersion: cfg.configuration_schema_version ?? null,
      });
    }
    if (required.has('quantity') && quantity == null) {
      return emptyResult(raw, {
        status: 'INVALID',
        errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
        detail: 'quantity required',
        labelKind: 'ITEM',
        normalizedPayload: normalized,
        diagnostics,
        profileSource: 'SUPPLIER',
        profileId: input.profileId,
        profileVersion: input.profileVersion,
        configurationSchemaVersion: cfg.configuration_schema_version ?? null,
      });
    }
    // Never invent sku=label_id or quantity=1.
    if (isMinimal) {
      /* keep sku/quantity as extracted only */
    }
    if (!labelId && !sku) {
      return emptyResult(raw, {
        status: 'INVALID',
        errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
        detail: 'sku or label_id missing',
        labelKind: 'ITEM',
        normalizedPayload: normalized,
        diagnostics,
        profileSource: 'SUPPLIER',
        profileId: input.profileId,
        profileVersion: input.profileVersion,
        configurationSchemaVersion: cfg.configuration_schema_version ?? null,
      });
    }
    return emptyResult(raw, {
      status: 'VALID',
      labelKind: 'ITEM',
      normalizedPayload: normalized,
      labelId,
      sku,
      quantity,
      diagnostics: { ...diagnostics, identity_valid: true },
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  const positionId =
    (fields.position_id as string | null) || (fields.label_id as string | null) || null;
  if (!positionId) {
    return emptyResult(raw, {
      status: 'INVALID',
      errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
      detail: 'position_id required',
      labelKind: 'POSITION',
      normalizedPayload: normalized,
      diagnostics,
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }
  return emptyResult(raw, {
    status: 'VALID',
    labelKind: 'POSITION',
    normalizedPayload: normalized,
    positionId,
    pallet: (fields.pallet as string | null) ?? null,
    side: (fields.side as string | null) ?? null,
    level: (fields.level as string | null) ?? null,
    diagnostics: { ...diagnostics, identity_valid: true },
    profileSource: 'SUPPLIER',
    profileId: input.profileId,
    profileVersion: input.profileVersion,
    configurationSchemaVersion: cfg.configuration_schema_version ?? null,
  });
}
