// Auth API client for v3.2.1 — Phase 1 foundation only.
// Functions are defined with correct contracts but deliberately not implemented yet.

import type {
  AuthUser,
  LoginRequestDto,
  LoginResponseDto,
  AuthErrorResponseDto,
} from './types';

export async function login(_payload: LoginRequestDto): Promise<LoginResponseDto> {
  // Phase 1: contract only. Real implementation will be added in Phase 2.
  throw new Error('Auth login is not implemented in v3.2.1 Phase 1.');
}

export async function getCurrentUser(): Promise<AuthUser> {
  // Phase 1: contract only. Implementation will call /auth/me in later phases.
  throw new Error('Auth current-user lookup is not implemented in v3.2.1 Phase 1.');
}

export function isAuthError(_error: unknown): _error is AuthErrorResponseDto {
  // Helper boundary for later phases. Currently a simple structural check.
  return false;
}

