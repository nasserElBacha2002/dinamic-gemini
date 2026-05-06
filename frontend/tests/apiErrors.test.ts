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

  it('maps known ApiError detail when code is missing', () => {
    const error = new ApiError('forbidden', 403, { detail: 'Forbidden' });
    expect(getVisibleErrorMessage(error, 'inventory')).toBe(i18n.t('errors.forbidden'));
  });

  it('uses safe contextual fallback for unknown ApiError code/detail', () => {
    const error = new ApiError('internal trace id: x-123', 500, {
      code: 'UNKNOWN_BACKEND_CODE',
      detail: 'very technical backend failure detail',
    });
    const message = getVisibleErrorMessage(error, 'analytics');
    expect(message).toBe(i18n.t('errors.load_metrics'));
    expect(message).not.toContain('UNKNOWN_BACKEND_CODE');
    expect(message).not.toContain('internal stack trace');
    expect(message).not.toContain('trace id');
  });

  it('does not expose stack-like Error message and falls back safely', () => {
    const error = new Error('TypeError: cannot read property x of undefined at file.ts:22');
    const message = getVisibleErrorMessage(error);
    expect(message).toBe(i18n.t('errors.generic'));
    expect(message).not.toContain('TypeError');
    expect(message).not.toContain('file.ts');
    expect(message).not.toContain('undefined');
    expect(message).not.toContain('stack');
  });

  it('handles string errors without exposing raw content', () => {
    const message = getVisibleErrorMessage('raw backend failed', 'inventory');
    expect(message).toBe(i18n.t('errors.load_inventory'));
    expect(message).not.toContain('raw backend failed');
  });

  it('handles nullish without throwing', () => {
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
    const contexts: VisibleErrorContext[] = [
      'inventory',
      'aisle',
      'analytics',
      'reviewQueue',
      'results',
      'ingestionSession',
      'auth',
      'default',
    ];
    const expected = [
      i18n.t('errors.load_inventory'),
      i18n.t('errors.load_aisles'),
      i18n.t('errors.load_metrics'),
      i18n.t('errors.load_review_queue'),
      i18n.t('errors.load_results'),
      i18n.t('errors.request_failed'),
      i18n.t('errors.auth.fallback'),
      i18n.t('errors.generic'),
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
