import { describe, expect, it } from 'vitest';
import {
  isTooManyFilesForUpload,
  maxFilesPerUploadHelperText,
  tooManyFilesMessage,
} from '../src/utils/uploadFileLimits';
import { MAX_FILES_PER_UPLOAD } from '../src/constants/uploads';

describe('uploadFileLimits', () => {
  it('flags more than MAX_FILES_PER_UPLOAD', () => {
    expect(isTooManyFilesForUpload(MAX_FILES_PER_UPLOAD)).toBe(false);
    expect(isTooManyFilesForUpload(MAX_FILES_PER_UPLOAD + 1)).toBe(true);
  });

  it('returns Spanish aisle message', () => {
    expect(tooManyFilesMessage('aisle')).toContain('5');
    expect(tooManyFilesMessage('import')).toContain('5');
    expect(maxFilesPerUploadHelperText()).toContain('5');
  });
});
