/**
 * Offline supplier label recognition — deterministic subset mirroring backend
 * LabelValidationService / StructuredPayloadExtractor (MINIMAL / SIMPLE / SEGMENTED).
 * GS1 is intentionally NOT implemented in this phase.
 *
 * SEGMENTED order (must match backend):
 * structural trim → split → map → per-field identity normalize →
 * validate prefix/length/charset on identity field only → quantity/completeness.
 */

import {
  decideQuantityCompleteness,
  fallbackEligible,
} from './quantityCompleteness';

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
  quantity_rules?: {
    required?: boolean;
    expected_presence?: string | null;
    missing_quantity_action?: string | null;
    allow_external_fallback?: boolean;
    minimum?: number | null;
    maximum?: number | null;
    allow_negative?: boolean;
    allow_decimals?: boolean;
  } | null;
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

/** Full-payload normalization for SIMPLE identity payloads (backend parity). */
export function normalizeOfflinePayload(
  raw: string,
  rules: OfflineDeterministicRules | null | undefined,
): string {
  return normalizeFieldValue(normalizeStructural(raw, rules), rules);
}

/** Pre-split normalization — preserve delimiter and segment interiors. */
export function normalizeStructural(
  raw: string,
  rules: OfflineDeterministicRules | null | undefined,
): string {
  let value = raw ?? '';
  const norm = rules?.normalization ?? {};
  if (norm.trim_outer_whitespace !== false) {
    value = value.trim();
  }
  return value;
}

/** Per-field identity normalization after structural mapping. */
export function normalizeFieldValue(
  value: string,
  rules: OfflineDeterministicRules | null | undefined,
): string {
  let text = value ?? '';
  const norm = rules?.normalization ?? {};
  if (norm.trim_outer_whitespace !== false) {
    text = text.trim();
  }
  if (norm.remove_internal_spaces) text = text.replace(/\s+/g, '');
  if (norm.remove_hyphens) text = text.replace(/-/g, '');
  const caseMode = String(norm.case_normalization ?? 'NONE').toUpperCase();
  if (caseMode === 'UPPER') text = text.toUpperCase();
  if (caseMode === 'LOWER') text = text.toLowerCase();
  return text;
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

type ExtractOutcome = {
  fields: Record<string, string | number | null>;
  structuralPayload: string;
  meta: Record<string, string>;
};

function extractFields(
  raw: string,
  rules: OfflineDeterministicRules,
  labelKind: 'ITEM' | 'POSITION',
): ExtractOutcome {
  const structure = String(rules.payload_structure ?? 'SIMPLE').toUpperCase();
  const mappings = rules.field_mappings ?? [];
  const out: Record<string, string | number | null> = {};

  if (structure === 'GS1') {
    throw new Error('GS1_NOT_SUPPORTED_OFFLINE');
  }

  if (structure === 'SEGMENTED') {
    const structural = normalizeStructural(raw, rules);
    const delimiter = rules.delimiter ?? '|';
    const delimiterDetected = structural.includes(delimiter);
    if (
      rules.expected_segment_count != null &&
      Number(rules.expected_segment_count) > 1 &&
      !delimiterDetected
    ) {
      throw Object.assign(new Error('delimiter not found in payload'), {
        code: 'LABEL_SEGMENT_COUNT_MISMATCH',
      });
    }
    const parts = structural.split(delimiter);
    if (parts.length > 32) {
      throw Object.assign(new Error('segment count exceeds limit'), {
        code: 'LABEL_SEGMENT_COUNT_MISMATCH',
      });
    }
    if (
      rules.expected_segment_count != null &&
      parts.length !== Number(rules.expected_segment_count)
    ) {
      throw Object.assign(
        new Error(
          `expected ${rules.expected_segment_count} segments, got ${parts.length}`,
        ),
        { code: 'LABEL_SEGMENT_COUNT_MISMATCH' },
      );
    }
    for (const mapping of mappings) {
      if (String(mapping.source).toUpperCase() !== 'SEGMENT') continue;
      const idx = mapping.segment_index;
      if (idx == null || idx < 0 || idx >= parts.length) {
        throw Object.assign(
          new Error(`segment index ${String(idx)} out of range`),
          { code: 'LABEL_SEGMENT_COUNT_MISMATCH' },
        );
      }
      const target = String(mapping.target).toLowerCase();
      const segmentValue = parts[idx] ?? '';
      if (!String(segmentValue).trim()) {
        throw Object.assign(new Error(`mapped segment for ${target} is empty`), {
          code: 'LABEL_REQUIRED_FIELD_MISSING',
        });
      }
      if (target === 'quantity') {
        out.quantity = parseIntegerQuantityOrThrow(String(segmentValue).trim());
      } else {
        out[target] = normalizeFieldValue(segmentValue, rules);
      }
    }
    return {
      fields: out,
      structuralPayload: structural,
      meta: {
        payload_structure: 'SEGMENTED',
        delimiter_detected: delimiterDetected ? 'true' : 'false',
        segment_count: String(parts.length),
        mapped_fields: Object.keys(out)
          .filter((k) => out[k] != null && out[k] !== '')
          .sort()
          .join(','),
      },
    };
  }

  // SIMPLE: full identity normalization applies to the whole payload.
  const normalized = normalizeOfflinePayload(raw, rules);
  for (const mapping of mappings) {
    if (String(mapping.source).toUpperCase() !== 'WHOLE') continue;
    const target = String(mapping.target).toLowerCase();
    if (target === 'quantity') {
      const qtyText = String(normalized).trim();
      if (!qtyText) {
        out.quantity = null;
      } else {
        out.quantity = parseIntegerQuantityOrThrow(qtyText);
      }
    } else {
      out[target] = normalized;
    }
  }
  if (mappings.length === 0) {
    if (labelKind === 'POSITION') out.position_id = normalized;
    else out.label_id = normalized;
  }
  return {
    fields: out,
    structuralPayload: normalized,
    meta: {
      payload_structure: 'SIMPLE',
      mapped_fields: Object.keys(out)
        .filter((k) => out[k] != null && out[k] !== '')
        .sort()
        .join(','),
    },
  };
}

function identityShapeSubject(
  labelKind: 'ITEM' | 'POSITION',
  structure: string,
  structuralPayload: string,
  fields: Record<string, string | number | null>,
): { value: string; field: string } {
  if (structure === 'SEGMENTED') {
    if (labelKind === 'ITEM') {
      const labelId = String(fields.label_id ?? '').trim();
      if (labelId) return { value: labelId, field: 'label_id' };
      const sku = String(fields.sku ?? '').trim();
      if (sku) return { value: sku, field: 'sku' };
      return { value: '', field: 'label_id' };
    }
    const positionId = String(fields.position_id ?? fields.label_id ?? '').trim();
    return { value: positionId, field: 'position_id' };
  }
  return { value: structuralPayload, field: 'payload' };
}

function parseIntegerQuantityOrThrow(qtyText: string): number {
  if (!/^-?\d+$/.test(qtyText)) {
    throw Object.assign(new Error('quantity must be an integer'), {
      code: 'LABEL_FIELD_INVALID',
    });
  }
  const n = Number(qtyText);
  if (!Number.isInteger(n)) {
    throw Object.assign(new Error('quantity decimals are not allowed'), {
      code: 'LABEL_FIELD_INVALID',
    });
  }
  return n;
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

  let extracted: ExtractOutcome;
  try {
    extracted = extractFields(raw, rules, input.labelKind);
  } catch (e) {
    const code = (e as { code?: string }).code ?? 'TECHNICAL_ERROR';
    const structural = normalizeStructural(raw, rules);
    return emptyResult(raw, {
      status:
        code === 'LABEL_SEGMENT_COUNT_MISMATCH' ||
        code === 'LABEL_REQUIRED_FIELD_MISSING' ||
        code === 'LABEL_FIELD_INVALID'
          ? 'NOT_APPLICABLE'
          : 'TECHNICAL_ERROR',
      errorCode: code,
      detail: e instanceof Error ? e.message : 'extract failed',
      labelKind: input.labelKind,
      normalizedPayload: structural,
      diagnostics: {
        payload_structure: structure,
        validation_error_code: code,
      },
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  const { fields, structuralPayload, meta } = extracted;
  const subject = identityShapeSubject(
    input.labelKind,
    structure,
    structuralPayload,
    fields,
  );
  const diagnostics: Record<string, unknown> = {
    ...meta,
    failed_field: subject.field,
    found: subject.value,
    prefix: {
      expected: rules.expected_prefix ?? null,
      pass: true,
    },
    length: {
      found: subject.value.length,
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

  if (!subject.value) {
    return emptyResult(raw, {
      status: 'INVALID',
      errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
      detail: `identity field ${subject.field} missing after structured extraction`,
      labelKind: input.labelKind,
      normalizedPayload: structuralPayload,
      diagnostics: {
        ...diagnostics,
        validation_error_code: 'LABEL_REQUIRED_FIELD_MISSING',
      },
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  const prefix = (rules.expected_prefix || '').trim();
  if (prefix && !subject.value.startsWith(prefix)) {
    (diagnostics.prefix as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_PREFIX_MISMATCH',
      detail: `PREFIX_MISMATCH on ${subject.field}: expected ${prefix}`,
      labelKind: input.labelKind,
      normalizedPayload: structuralPayload,
      diagnostics: {
        ...diagnostics,
        validation_error_code: 'LABEL_PREFIX_MISMATCH',
      },
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }
  const suffix = (rules.expected_suffix || '').trim();
  if (suffix && !subject.value.endsWith(suffix)) {
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_SUFFIX_MISMATCH',
      detail: `suffix mismatch on ${subject.field}`,
      labelKind: input.labelKind,
      normalizedPayload: structuralPayload,
      diagnostics: {
        ...diagnostics,
        validation_error_code: 'LABEL_SUFFIX_MISMATCH',
      },
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  const length = subject.value.length;
  if (rules.exact_length != null && length !== Number(rules.exact_length)) {
    (diagnostics.length as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_LENGTH_MISMATCH',
      detail: `LENGTH_MISMATCH on ${subject.field}: expected ${rules.exact_length}, found ${length}`,
      labelKind: input.labelKind,
      normalizedPayload: structuralPayload,
      diagnostics: {
        ...diagnostics,
        validation_error_code: 'LABEL_LENGTH_MISMATCH',
      },
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
      detail: `min_length on ${subject.field}`,
      labelKind: input.labelKind,
      normalizedPayload: structuralPayload,
      diagnostics: {
        ...diagnostics,
        validation_error_code: 'LABEL_LENGTH_MISMATCH',
      },
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
      detail: `max_length on ${subject.field}`,
      labelKind: input.labelKind,
      normalizedPayload: structuralPayload,
      diagnostics: {
        ...diagnostics,
        validation_error_code: 'LABEL_LENGTH_MISMATCH',
      },
      profileSource: 'SUPPLIER',
      profileId: input.profileId,
      profileVersion: input.profileVersion,
      configurationSchemaVersion: cfg.configuration_schema_version ?? null,
    });
  }

  if (!charsetOk(subject.value, rules.character_set ?? null)) {
    (diagnostics.charset as { pass: boolean }).pass = false;
    return emptyResult(raw, {
      status: 'NOT_APPLICABLE',
      errorCode: 'LABEL_CHARSET_MISMATCH',
      detail: `CHARSET_MISMATCH on ${subject.field}`,
      labelKind: input.labelKind,
      normalizedPayload: structuralPayload,
      diagnostics: {
        ...diagnostics,
        validation_error_code: 'LABEL_CHARSET_MISMATCH',
      },
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
    const sku =
      (fields.sku as string | null) || (fields.internal_code as string | null) || null;
    const quantity: number | null =
      typeof fields.quantity === 'number' ? fields.quantity : null;
    const qrules = cfg.quantity_rules ?? null;
    if (quantity != null) {
      if (quantity < 0 && !qrules?.allow_negative) {
        return emptyResult(raw, {
          status: 'INVALID',
          errorCode: 'LABEL_FIELD_INVALID',
          detail: 'quantity must not be negative',
          labelKind: 'ITEM',
          normalizedPayload: structuralPayload,
          diagnostics: { ...diagnostics, failed_field: 'quantity' },
          profileSource: 'SUPPLIER',
          profileId: input.profileId,
          profileVersion: input.profileVersion,
          configurationSchemaVersion: cfg.configuration_schema_version ?? null,
        });
      }
      const minimum = qrules?.minimum ?? 1;
      const maximum = qrules?.maximum ?? 99_999_999;
      if (quantity === 0 && Number(minimum) >= 1 && !qrules?.allow_negative) {
        return emptyResult(raw, {
          status: 'INVALID',
          errorCode: 'LABEL_FIELD_INVALID',
          detail: 'quantity must be a positive integer',
          labelKind: 'ITEM',
          normalizedPayload: structuralPayload,
          diagnostics: { ...diagnostics, failed_field: 'quantity' },
          profileSource: 'SUPPLIER',
          profileId: input.profileId,
          profileVersion: input.profileVersion,
          configurationSchemaVersion: cfg.configuration_schema_version ?? null,
        });
      }
      if (quantity < Number(minimum)) {
        return emptyResult(raw, {
          status: 'INVALID',
          errorCode: 'LABEL_FIELD_INVALID',
          detail: `quantity below minimum ${String(minimum)}`,
          labelKind: 'ITEM',
          normalizedPayload: structuralPayload,
          diagnostics: { ...diagnostics, failed_field: 'quantity' },
          profileSource: 'SUPPLIER',
          profileId: input.profileId,
          profileVersion: input.profileVersion,
          configurationSchemaVersion: cfg.configuration_schema_version ?? null,
        });
      }
      if (quantity > Number(maximum)) {
        return emptyResult(raw, {
          status: 'INVALID',
          errorCode: 'LABEL_FIELD_INVALID',
          detail: `quantity above maximum ${String(maximum)}`,
          labelKind: 'ITEM',
          normalizedPayload: structuralPayload,
          diagnostics: { ...diagnostics, failed_field: 'quantity' },
          profileSource: 'SUPPLIER',
          profileId: input.profileId,
          profileVersion: input.profileVersion,
          configurationSchemaVersion: cfg.configuration_schema_version ?? null,
        });
      }
    }
    if (required.has('label_id') && !labelId) {
      return emptyResult(raw, {
        status: 'INVALID',
        errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
        detail: 'label_id required',
        labelKind: 'ITEM',
        normalizedPayload: structuralPayload,
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
        normalizedPayload: structuralPayload,
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
        normalizedPayload: structuralPayload,
        diagnostics,
        profileSource: 'SUPPLIER',
        profileId: input.profileId,
        profileVersion: input.profileVersion,
        configurationSchemaVersion: cfg.configuration_schema_version ?? null,
      });
    }
    // Never invent sku=label_id or quantity=0/1.
    if (isMinimal) {
      /* keep sku/quantity as extracted only */
    }
    if (!labelId && !sku) {
      return emptyResult(raw, {
        status: 'INVALID',
        errorCode: 'LABEL_REQUIRED_FIELD_MISSING',
        detail: 'sku or label_id missing',
        labelKind: 'ITEM',
        normalizedPayload: structuralPayload,
        diagnostics,
        profileSource: 'SUPPLIER',
        profileId: input.profileId,
        profileVersion: input.profileVersion,
        configurationSchemaVersion: cfg.configuration_schema_version ?? null,
      });
    }
    const qtyDecision = decideQuantityCompleteness({
      kind: 'ITEM',
      required: Boolean(cfg.quantity_rules?.required),
      expected_presence: cfg.quantity_rules?.expected_presence,
      missing_quantity_action: cfg.quantity_rules?.missing_quantity_action,
      allow_external_fallback: Boolean(cfg.quantity_rules?.allow_external_fallback),
      required_fields: cfg.required_fields,
    });
    const requiredFields = new Set(
      (cfg.required_fields ?? ['label_id']).map((f) => String(f).toLowerCase()),
    );
    const missingCompletion: string[] = [];
    if (requiredFields.has('label_id') && !labelId && !sku) {
      missingCompletion.push('label_id');
    }
    if ((requiredFields.has('sku') || requiredFields.has('internal_code')) && !sku && !labelId) {
      missingCompletion.push('sku');
    }
    if (qtyDecision.quantity_required_for_completion && quantity == null) {
      missingCompletion.push('quantity');
    }
    const identityComplete = Boolean(labelId || sku);
    const completionComplete = identityComplete && missingCompletion.length === 0;
    return emptyResult(raw, {
      status: 'VALID',
      labelKind: 'ITEM',
      normalizedPayload: structuralPayload,
      labelId,
      sku,
      quantity,
      diagnostics: {
        ...diagnostics,
        identity_valid: identityComplete,
        identity_complete: identityComplete,
        completion_complete: completionComplete,
        persistence_complete: completionComplete,
        enrichment_complete: completionComplete,
        missing_completion_fields: missingCompletion,
        missing_persistence_fields: missingCompletion,
        fallback_eligible: fallbackEligible(qtyDecision, {
          identityComplete,
          quantityPresent: quantity != null,
        }),
        quantity_status: quantity == null ? 'MISSING' : 'PRESENT',
        quantity_source: quantity == null ? null : 'CODE_SCAN',
      },
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
      normalizedPayload: structuralPayload,
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
    normalizedPayload: structuralPayload,
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
