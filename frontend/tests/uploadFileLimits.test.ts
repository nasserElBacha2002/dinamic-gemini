import { describe, expect, it } from 'vitest';
import {
  isTooManyFilesForUpload,
  maxFilesPerUploadHelperText,
} from '../src/utils/uploadFileLimits';
import { UPLOAD_LIMITS } from '../src/features/uploads/bulkUpload.config';

describe('uploadFileLimits', () => {
  it('flags more than maxFilesPerRequest (per HTTP request only)', () => {
    expect(isTooManyFilesForUpload(UPLOAD_LIMITS.maxFilesPerRequest)).toBe(false);
    expect(isTooManyFilesForUpload(UPLOAD_LIMITS.maxFilesPerRequest + 1)).toBe(true);
  });

  it('helper text includes configured count', () => {
    expect(maxFilesPerUploadHelperText()).toContain(String(UPLOAD_LIMITS.maxFilesPerRequest));
  });
});
