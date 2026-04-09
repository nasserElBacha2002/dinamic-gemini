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
