/**
 * Centralized API error message extraction for v3 frontend.
 * Supports FastAPI detail as string, validation array, and non-JSON errors.
 */

import i18n from '../i18n';
import { ApiError } from '../api/types';
import {
  authErrorCodeToTranslationKey,
  backendDetailToTranslationKey,
  v3StructuredErrorCodeToTranslationKey,
} from './errorTranslations';

/**
 * FastAPI validation error item shape.
 */
interface ValidationErrorItem {
  msg?: string;
  loc?: unknown;
  type?: string;
}

function isValidationDetail(detail: unknown): detail is ValidationErrorItem[] {
  return Array.isArray(detail) && detail.length > 0;
}

function messageFromValidationItem(item: ValidationErrorItem): string {
  if (typeof item.msg === 'string' && item.msg.trim()) {
    return item.msg;
  }
  return i18n.t('errors.validation_generic');
}

/**
 * Extracts a raw message from an API error or unknown throwable (often English from the server).
 * Prefer `resolveApiErrorMessage` for UI.
 */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.data?.detail !== undefined) {
    const detail = error.data.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail.trim();
    }
    if (isValidationDetail(detail)) {
      const first = detail[0];
      return first && typeof first === 'object'
        ? messageFromValidationItem(first as ValidationErrorItem)
        : i18n.t('errors.validation_generic');
    }
    return error.message || fallback;
  }
  if (error instanceof Error && error.message?.trim()) {
    return error.message.trim();
  }
  if (typeof error === 'string' && error.trim()) {
    return error.trim();
  }
  return fallback;
}

export type VisibleErrorContext =
  | 'default'
  | 'auth'
  | 'inventory'
  | 'aisle'
  | 'analytics'
  | 'results'
  | 'ingestionSession';

const CONTEXT_FALLBACK_KEY: Record<VisibleErrorContext, string> = {
  default: 'errors.generic',
  auth: 'errors.auth.fallback',
  inventory: 'errors.load_inventory',
  aisle: 'errors.load_aisles',
  analytics: 'errors.load_metrics',
  results: 'errors.load_results',
  ingestionSession: 'errors.request_failed',
};

interface AuthErrorEnvelopeLike {
  error?: {
    code?: unknown;
    message?: unknown;
  };
}

interface AuthApiErrorLike {
  responseBody?: AuthErrorEnvelopeLike;
}

function isAuthApiErrorLike(value: unknown): value is AuthApiErrorLike {
  if (!value || typeof value !== 'object') return false;
  return 'responseBody' in value;
}

function safeTrimmedString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function authVisibleMessage(error: AuthApiErrorLike, fallbackKey: string): string {
  const authCode = safeTrimmedString(error.responseBody?.error?.code);
  if (authCode) {
    const byCode = authErrorCodeToTranslationKey(authCode) ?? null;
    if (byCode) return i18n.t(byCode);
  }
  const authMessage = safeTrimmedString(error.responseBody?.error?.message);
  if (authMessage) {
    const mapped = backendDetailToTranslationKey(authMessage);
    if (mapped) return i18n.t(mapped);
  }
  return i18n.t(fallbackKey);
}

/**
 * Public entry point for user-visible error messages.
 * Always returns localized safe copy and avoids exposing technical raw error text.
 */
export function getVisibleErrorMessage(
  error: unknown,
  context: VisibleErrorContext = 'default'
): string {
  const fallbackKey = CONTEXT_FALLBACK_KEY[context] ?? CONTEXT_FALLBACK_KEY.default;

  if (error instanceof ApiError && typeof error.data?.code === 'string' && error.data.code.trim()) {
    const byCode = v3StructuredErrorCodeToTranslationKey(error.data.code);
    if (byCode) return i18n.t(byCode);
  }

  if (isAuthApiErrorLike(error)) {
    return authVisibleMessage(error, fallbackKey);
  }

  const raw = getApiErrorMessage(error, '');
  const mapped = raw.trim() ? backendDetailToTranslationKey(raw) : null;
  if (mapped) return i18n.t(mapped);

  return i18n.t(fallbackKey);
}

/** User-facing Spanish message: maps known backend text to i18n; otherwise generic fallback. */
export function resolveApiErrorMessage(error: unknown, fallbackKey: string): string {
  const visible = getVisibleErrorMessage(error, 'default');
  if (visible !== i18n.t(CONTEXT_FALLBACK_KEY.default)) return visible;
  return i18n.t(fallbackKey);
}
