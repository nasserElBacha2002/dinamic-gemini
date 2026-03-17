// Auth types for v3.2.1 — Minimal Administrative Authentication (Phase 1).
// Contracts mirror the backend auth schemas. Phase 1 defines shape only.

export type AuthRole = 'administrator';

export interface AuthUser {
  id: string;
  username: string;
  role: AuthRole;
}

export interface LoginRequestDto {
  username: string;
  password: string;
}

export interface LoginResponseDto {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  /**
   * Optional refresh token for session renewal (v3.2.3.E6).
   * Older backends may omit this field.
   */
  refresh_token?: string | null;
  user: AuthUser;
}

export interface AuthErrorPayload {
  code: string;
  message: string;
}

export interface AuthErrorResponseDto {
  error: AuthErrorPayload;
}

