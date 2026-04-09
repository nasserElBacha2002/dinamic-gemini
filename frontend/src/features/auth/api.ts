/**
 * Auth API client for v3.2.1 — Phase 4 implementation.
 * Calls POST /auth/login and GET /auth/me; parses stable auth error envelope.
 */

import type {
  AuthUser,
  LoginRequestDto,
  LoginResponseDto,
  AuthErrorResponseDto,
} from './types';
import i18n from '../../i18n';
import { authErrorCodeToTranslationKey, backendDetailToTranslationKey } from '../../utils/errorTranslations';

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '';

/** Thrown when the backend returns the stable auth error envelope (e.g. 401). */
export class AuthApiError extends Error {
  constructor(
    message: string,
    public readonly responseBody: AuthErrorResponseDto,
  ) {
    super(message);
    this.name = 'AuthApiError';
    Object.setPrototypeOf(this, AuthApiError.prototype);
  }
}

function isAuthErrorEnvelope(data: unknown): data is AuthErrorResponseDto {
  const body = data as AuthErrorResponseDto;
  return !!(
    body?.error &&
    typeof body.error === 'object' &&
    'code' in body.error &&
    'message' in body.error
  );
}

async function handleAuthResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }

  if (!response.ok) {
    if (isAuthErrorEnvelope(data)) {
      throw new AuthApiError((data as AuthErrorResponseDto).error.message, data as AuthErrorResponseDto);
    }
    throw new Error(
      typeof (data as { detail?: string })?.detail === 'string'
        ? (data as { detail: string }).detail
        : response.statusText || 'Request failed',
    );
  }

  return data as T;
}

export async function login(payload: LoginRequestDto): Promise<LoginResponseDto> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleAuthResponse<LoginResponseDto>(response);
}

/**
 * Validate token and return current user. Use for session restoration.
 * Call with the stored token; backend returns 401 if invalid/expired.
 */
export async function getCurrentUser(token: string): Promise<AuthUser> {
  const response = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleAuthResponse<AuthUser>(response);
}

export function isAuthError(error: unknown): error is AuthApiError {
  return error instanceof AuthApiError;
}

/** Get user-facing message from an auth API error (localized). */
export function getAuthErrorMessage(error: unknown): string {
  if (error instanceof AuthApiError) {
    const codeKey = authErrorCodeToTranslationKey(error.responseBody.error.code);
    if (codeKey) return i18n.t(codeKey);
    const detailKey = backendDetailToTranslationKey(error.responseBody.error.message);
    if (detailKey) return i18n.t(detailKey);
    return i18n.t('errors.generic');
  }
  if (error instanceof Error && error.message?.trim()) {
    const detailKey = backendDetailToTranslationKey(error.message);
    if (detailKey) return i18n.t(detailKey);
    return error.message.trim();
  }
  return i18n.t('errors.auth.fallback');
}
