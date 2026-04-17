/**
 * Centralized API error message extraction for v3 frontend.
 * Supports FastAPI detail as string, validation array, and non-JSON errors.
 */

import i18n from '../i18n';
import { ApiError } from '../api/types';
import { backendDetailToTranslationKey, v3StructuredErrorCodeToTranslationKey } from './errorTranslations';

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

/** User-facing Spanish message: maps known backend text to i18n; otherwise generic fallback. */
export function resolveApiErrorMessage(error: unknown, fallbackKey: string): string {
  if (error instanceof ApiError && typeof error.data?.code === 'string' && error.data.code.trim()) {
    const byCode = v3StructuredErrorCodeToTranslationKey(error.data.code);
    if (byCode) return i18n.t(byCode);
  }
  const raw = getApiErrorMessage(error, '');
  if (!raw.trim()) return i18n.t(fallbackKey);
  const mapped = backendDetailToTranslationKey(raw);
  if (mapped) return i18n.t(mapped);
  return i18n.t('errors.generic');
}
