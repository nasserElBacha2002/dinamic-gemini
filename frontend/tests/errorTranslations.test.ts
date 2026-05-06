import { describe, expect, it } from 'vitest';
import {
  authErrorCodeToTranslationKey,
  backendDetailToTranslationKey,
  v3StructuredErrorCodeToTranslationKey,
} from '../src/utils/errorTranslations';

describe('errorTranslations mappings', () => {
  it('maps stable v3 structured codes', () => {
    expect(v3StructuredErrorCodeToTranslationKey('INVENTORY_NOT_FOUND')).toBe('errors.not_found');
    expect(v3StructuredErrorCodeToTranslationKey('INTERNAL_SERVER_ERROR')).toBe('errors.unexpected');
  });

  it('maps auth envelope codes', () => {
    expect(authErrorCodeToTranslationKey('INVALID_CREDENTIALS')).toBe('errors.auth.invalid_credentials');
    expect(authErrorCodeToTranslationKey('UNKNOWN_AUTH_CODE')).toBeNull();
  });

  it('maps known backend details and ignores unknown text', () => {
    expect(backendDetailToTranslationKey('Unauthorized')).toBe('errors.auth.unauthorized');
    expect(backendDetailToTranslationKey('some internal detail')).toBeNull();
  });
});
