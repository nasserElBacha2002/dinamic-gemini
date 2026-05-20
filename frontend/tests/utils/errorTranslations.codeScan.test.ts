import { describe, expect, it } from 'vitest';
import { ApiError } from '../../src/api/types';
import { getVisibleErrorMessage } from '../../src/utils/apiErrors';

describe('code scan error translations', () => {
  it('maps CODE_SCAN_SCANNER_UNAVAILABLE to Spanish copy', () => {
    const err = new ApiError('Code scan engine is unavailable', 503, {
      code: 'CODE_SCAN_SCANNER_UNAVAILABLE',
      detail: 'Code scan engine is unavailable',
    });
    const message = getVisibleErrorMessage(err, 'default');
    expect(message).toContain('motor de escaneo');
    expect(message).not.toContain('Code scan engine');
  });
});
