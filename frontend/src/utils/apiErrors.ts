/**
 * Centralized API error message extraction for v3 frontend.
 * Supports FastAPI detail as string, validation array, and non-JSON errors.
 */

import { ApiError } from '../api/types';

/**
 * FastAPI validation error item shape.
 */
interface ValidationErrorItem {
  msg?: string;
  loc?: unknown;
  type?: string;
}

function isValidationDetail(
  detail: unknown
): detail is ValidationErrorItem[] {
  return Array.isArray(detail) && detail.length > 0;
}

function messageFromValidationItem(item: ValidationErrorItem): string {
  if (typeof item.msg === 'string' && item.msg.trim()) {
    return item.msg;
  }
  return 'Validation error';
}

/**
 * Extracts a user-facing message from an API error or unknown throwable.
 *
 * - detail as string → use it
 * - detail as FastAPI validation array [{ msg: "..." }] → first message or "Validation error"
 * - ApiError with message → fallback to err.message
 * - Otherwise → fallback
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
        : 'Validation error';
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
