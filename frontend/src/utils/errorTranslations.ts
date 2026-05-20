/**
 * Maps stable backend / API error codes and common English detail strings to i18n keys.
 * Components should not branch on English text — only on keys returned here.
 *
 * Ownership: human-facing copy lives in frontend i18n locale JSON; this file only maps stable
 * wire code / detail fragments to translation keys. Backend API wire literals live in
 * backend/src/api/constants/error_wire.py and must never be imported from the frontend.
 */

const AUTH_CODE_TO_KEY: Record<string, string> = {
  INVALID_CREDENTIALS: 'errors.auth.invalid_credentials',
  UNAUTHORIZED: 'errors.auth.unauthorized',
  TOKEN_EXPIRED: 'errors.auth.token_expired',
  INVALID_TOKEN: 'errors.auth.invalid_token',
};

export function authErrorCodeToTranslationKey(code: string): string | null {
  const k = AUTH_CODE_TO_KEY[code.trim().toUpperCase()];
  return k ?? null;
}

/** v3 inventory API structured ``code`` → i18n (prefer over English ``detail`` matching). */
const V3_STRUCTURED_CODE_TO_KEY: Record<string, string> = {
  INVENTORY_NOT_FOUND: 'errors.not_found',
  AISLE_NOT_FOUND: 'errors.not_found',
  POSITION_NOT_FOUND: 'errors.not_found',
  PRODUCT_NOT_FOUND: 'errors.not_found',
  VISUAL_REFERENCE_NOT_FOUND: 'errors.not_found',
  ASSET_NOT_FOUND: 'errors.not_found',
  JOB_NOT_FOUND: 'errors.not_found',
  JOB_NOT_IN_AISLE_SCOPE: 'errors.not_found',
  ACTIVE_JOB_EXISTS: 'errors.generic',
  AISLE_SOURCE_ASSET_MUTATION_BLOCKED: 'errors.aisle_source_assets_locked',
  JOB_PROMOTION_NOT_ALLOWED: 'errors.promotion_failed',
  BENCHMARK_COMPARE_JOBS_MUST_DIFFER: 'errors.load_compare',
  ANALYTICS_SCOPE_VALIDATION_FAILED: 'errors.validation_generic',
  SUPPLIER_PROMPT_CONFIG_NOT_FOUND: 'clients.suppliers.prompt_configs.not_found_error',
  SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER: 'clients.suppliers.prompt_configs.invalid_provider_error',
  SUPPLIER_PROMPT_CONFIG_INVALID_MODEL: 'clients.suppliers.prompt_configs.invalid_model_error',
  SUPPLIER_PROMPT_CONFIG_EMPTY_INSTRUCTIONS: 'clients.suppliers.prompt_configs.blank_instructions_error',
  SUPPLIER_PROMPT_CONFIG_INVALID_SCOPE: 'clients.suppliers.prompt_configs.invalid_scope_error',
  SUPPLIER_PROMPT_CONFIG_ACTIVATION_FAILED: 'clients.suppliers.prompt_configs.activation_failed_error',
  INTERNAL_SERVER_ERROR: 'errors.unexpected',
  UPLOAD_TOO_MANY_FILES_PER_REQUEST: 'uploads.errors.tooManyFiles',
  AISLE_HAS_NO_SOURCE_ASSETS_FOR_CODE_SCAN: 'aisleCodeScans.errors.no_source_assets',
  CODE_SCAN_DISABLED: 'aisleCodeScans.errors.disabled',
  CODE_SCAN_MAX_ASSETS_EXCEEDED: 'aisleCodeScans.errors.max_assets',
  CODE_SCAN_SCANNER_UNAVAILABLE: 'aisleCodeScans.errors.scanner_unavailable',
  CODE_SCAN_EXPORT_NO_RUN: 'aisleCodeScans.errors.export_no_run',
  CODE_SCAN_EXPORT_UNSUPPORTED_TYPE: 'aisleCodeScans.errors.export_unsupported_type',
  CODE_SCAN_EXPORT_UNSUPPORTED_FORMAT: 'aisleCodeScans.errors.export_unsupported_format',
};

export function v3StructuredErrorCodeToTranslationKey(code: string): string | null {
  const k = V3_STRUCTURED_CODE_TO_KEY[code.trim()];
  return k ?? null;
}

const DETAIL_TO_KEY: [RegExp, string][] = [
  [/^invalid credentials\.?$/i, 'errors.auth.invalid_credentials'],
  [/^validation error$/i, 'errors.validation_generic'],
  [/^request failed$/i, 'errors.request_failed'],
  [/^too many files per upload request$/i, 'uploads.errors.tooManyFiles'],
  [/^authentication failed$/i, 'errors.auth.fallback'],
  [/^unauthorized$/i, 'errors.auth.unauthorized'],
  [/^not found$/i, 'errors.not_found'],
  [/^forbidden$/i, 'errors.forbidden'],
  [/^not allowed$/i, 'errors.forbidden'],
  [
    /^materialize this capture session group before preview\.?$/i,
    'ingestion_sessions.detail.grouping_preview_disabled_materialize',
  ],
  [/^this feature is only available for test inventories\.?$/i, 'errors.benchmark_requires_test_inventory'],
];

export function backendDetailToTranslationKey(detail: string): string | null {
  const t = detail.trim();
  if (!t) return null;
  for (const [re, key] of DETAIL_TO_KEY) {
    if (re.test(t)) return key;
  }
  return null;
}
