/**
 * v3.2.1 Phase 4 — auth storage and API helpers.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import * as storage from '../../src/features/auth/storage';
import { AuthApiError, isAuthError, getAuthErrorMessage } from '../../src/features/auth/api';

describe('auth storage', () => {
  beforeEach(() => {
    storage.clearStoredToken();
  });

  it('getStoredToken returns null when empty', () => {
    expect(storage.getStoredToken()).toBeNull();
  });

  it('setStoredToken and getStoredToken roundtrip', () => {
    storage.setStoredToken('abc');
    expect(storage.getStoredToken()).toBe('abc');
  });

  it('clearStoredToken removes token', () => {
    storage.setStoredToken('xyz');
    storage.clearStoredToken();
    expect(storage.getStoredToken()).toBeNull();
  });
});

describe('auth API helpers', () => {
  it('isAuthError returns true for AuthApiError', () => {
    const err = new AuthApiError('Invalid credentials.', {
      error: { code: 'INVALID_CREDENTIALS', message: 'Invalid credentials.' },
    });
    expect(isAuthError(err)).toBe(true);
    expect(getAuthErrorMessage(err)).toBe('Invalid credentials');
  });

  it('isAuthError returns false for plain Error', () => {
    expect(isAuthError(new Error('network'))).toBe(false);
    expect(getAuthErrorMessage(new Error('network'))).toBe('network');
  });

  it('getAuthErrorMessage returns fallback for unknown', () => {
    expect(getAuthErrorMessage(null)).toBe('Authentication failed');
  });
});
