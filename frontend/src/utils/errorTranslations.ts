/**
 * Maps stable backend / API error codes and common English detail strings to i18n keys.
 * Components should not branch on English text — only on keys returned here.
 */

const AUTH_CODE_TO_KEY: Record<string, string> = {
  INVALID_CREDENTIALS: 'errors.auth.invalid_credentials',
  UNAUTHORIZED: 'errors.auth.unauthorized',
  TOKEN_EXPIRED: 'errors.auth.token_expired',
  INVALID_TOKEN: 'errors.auth.invalid_token',
};

export function authErrorCodeToTranslationKey(code: string): string | null {
  const k = AUTH_CODE_TO_KEY[code.trim()];
  return k ?? null;
}

/** v3 inventory API structured ``code`` → i18n (prefer over English ``detail`` matching). */
const V3_STRUCTURED_CODE_TO_KEY: Record<string, string> = {
  INVENTORY_NOT_FOUND: 'errors.not_found',
  AISLE_NOT_FOUND: 'errors.not_found',
  POSITION_NOT_FOUND: 'errors.not_found',
  PRODUCT_NOT_FOUND: 'errors.not_found',
  VISUAL_REFERENCE_NOT_FOUND: 'errors.not_found',
  JOB_NOT_FOUND: 'errors.not_found',
  JOB_NOT_IN_AISLE_SCOPE: 'errors.not_found',
  ACTIVE_JOB_EXISTS: 'errors.generic',
  JOB_PROMOTION_NOT_ALLOWED: 'errors.promotion_failed',
  BENCHMARK_COMPARE_JOBS_MUST_DIFFER: 'errors.load_compare',
  ANALYTICS_SCOPE_VALIDATION_FAILED: 'errors.validation_generic',
  INTERNAL_SERVER_ERROR: 'errors.unexpected',
};

export function v3StructuredErrorCodeToTranslationKey(code: string): string | null {
  const k = V3_STRUCTURED_CODE_TO_KEY[code.trim()];
  return k ?? null;
}

const DETAIL_TO_KEY: [RegExp, string][] = [
  [/^invalid credentials\.?$/i, 'errors.auth.invalid_credentials'],
  [/^validation error$/i, 'errors.validation_generic'],
  [/^request failed$/i, 'errors.request_failed'],
  [/^authentication failed$/i, 'errors.auth.fallback'],
  [/^unauthorized$/i, 'errors.auth.unauthorized'],
  [/^not found$/i, 'errors.not_found'],
  [/^forbidden$/i, 'errors.forbidden'],
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
