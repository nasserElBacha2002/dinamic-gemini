import { describe, it, expect } from 'vitest';
import i18n from '../../src/i18n';
import { AuthApiError, getAuthErrorMessage } from '../../src/features/auth/api';

describe('auth api error compatibility', () => {
  it('maps invalid credentials from AuthApiError envelope', () => {
    const error = new AuthApiError('Invalid credentials.', {
      error: { code: 'INVALID_CREDENTIALS', message: 'Invalid credentials.' },
    });

    expect(getAuthErrorMessage(error)).toBe(i18n.t('errors.auth.invalid_credentials'));
  });

  it('does not expose raw technical message for unknown errors', () => {
    expect(getAuthErrorMessage(new Error('technical stack trace'))).toBe(i18n.t('errors.auth.fallback'));
  });
});

