import { describe, expect, it } from 'vitest';
import { ApiError } from '../src/api/types';
import i18n from '../src/i18n';
import {
  getVisibleErrorMessage,
  resolveApiErrorMessage,
  type VisibleErrorContext,
} from '../src/utils/apiErrors';

describe('getVisibleErrorMessage', () => {
  it('maps known ApiError code to translated key', () => {
    const error = new ApiError('not found', 404, { code: 'INVENTORY_NOT_FOUND' });
    expect(getVisibleErrorMessage(error)).toBe(i18n.t('errors.not_found'));
  });

  it('uses safe contextual fallback for unknown ApiError code/detail', () => {
    const error = new ApiError('internal trace id: x-123', 500, {
      code: 'UNKNOWN_BACKEND_CODE',
      detail: 'very technical backend failure detail',
    });
    expect(getVisibleErrorMessage(error, 'analytics')).toBe(i18n.t('errors.load_metrics'));
  });

  it('does not expose stack-like Error message and falls back safely', () => {
    const error = new Error('TypeError: cannot read property x of undefined at file.ts:22');
    expect(getVisibleErrorMessage(error)).toBe(i18n.t('errors.generic'));
  });

  it('handles string and nullish without throwing', () => {
    expect(getVisibleErrorMessage('some raw message')).toBe(i18n.t('errors.generic'));
    expect(getVisibleErrorMessage(null)).toBe(i18n.t('errors.generic'));
    expect(getVisibleErrorMessage(undefined)).toBe(i18n.t('errors.generic'));
  });

  it('uses auth fallback and supports auth envelope code mapping', () => {
    const authLikeError = {
      responseBody: {
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'Invalid credentials.',
        },
      },
    };
    expect(getVisibleErrorMessage(authLikeError, 'auth')).toBe(i18n.t('errors.auth.invalid_credentials'));
  });

  it('supports explicit context fallbacks', () => {
    const error = new Error('network unstable');
    const contexts: VisibleErrorContext[] = ['inventory', 'ingestionSession', 'reviewQueue', 'results'];
    const expected = [
      i18n.t('errors.load_inventory'),
      i18n.t('errors.request_failed'),
      i18n.t('errors.load_review_queue'),
      i18n.t('errors.load_results'),
    ];
    expect(contexts.map((ctx) => getVisibleErrorMessage(error, ctx))).toEqual(expected);
  });
});

describe('resolveApiErrorMessage compatibility', () => {
  it('keeps known mapping behavior', () => {
    const known = new ApiError('forbidden', 403, { detail: 'Forbidden' });
    expect(resolveApiErrorMessage(known, 'errors.request_failed')).toBe(i18n.t('errors.forbidden'));
  });

  it('keeps fallbackKey behavior when generic fallback is hit', () => {
    const unknown = new Error('opaque failure');
    expect(resolveApiErrorMessage(unknown, 'errors.load_compare')).toBe(i18n.t('errors.load_compare'));
  });
});
