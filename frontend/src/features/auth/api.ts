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
import { AUTH_LOGIN_PATH, AUTH_ME_PATH } from '../../constants/authApiPaths';
import { getVisibleErrorMessage } from '../../utils/apiErrors';
import { parseResponseJson, throwApiErrorIfNotOk } from '../../api/http';
import type { ApiErrorDetail } from '../../api/types';

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
  const data = parseResponseJson<unknown>(text);

  if (!response.ok) {
    if (isAuthErrorEnvelope(data)) {
      throw new AuthApiError((data as AuthErrorResponseDto).error.message, data as AuthErrorResponseDto);
    }
    throwApiErrorIfNotOk(response, text, data as ApiErrorDetail);
  }

  return data as T;
}

export async function login(payload: LoginRequestDto): Promise<LoginResponseDto> {
  const response = await fetch(`${API_BASE}${AUTH_LOGIN_PATH}`, {
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
  const response = await fetch(`${API_BASE}${AUTH_ME_PATH}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleAuthResponse<AuthUser>(response);
}

export function isAuthError(error: unknown): error is AuthApiError {
  return error instanceof AuthApiError;
}

/** Get user-facing message from an auth API error (localized). */
export function getAuthErrorMessage(error: unknown): string {
  return getVisibleErrorMessage(error, 'auth');
}
