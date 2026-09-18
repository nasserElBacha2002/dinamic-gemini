/**
 * Light vs strong READY integrity — same-size SHA mismatch, missing file,
 * digest capability/IO must not be confirmed integrity failures.
 */

import {
  DigestCapabilityError,
  DigestIoError,
} from '../src/features/exportPrep/digestAbsoluteFile';
import {
  isConfirmedReadyIntegrityFailure,
  validateReadyStaging,
} from '../src/features/exportPrep/validateReadyStaging';

jest.mock('expo-file-system', () => ({
  documentDirectory: 'file:///docs/',
  EncodingType: { UTF8: 'utf8', Base64: 'base64' },
  getInfoAsync: jest.fn(),
  makeDirectoryAsync: jest.fn(async () => undefined),
  copyAsync: jest.fn(async () => undefined),
  moveAsync: jest.fn(async () => undefined),
  deleteAsync: jest.fn(async () => undefined),
  readAsStringAsync: jest.fn(async () => Buffer.from('hello').toString('base64')),
  readDirectoryAsync: jest.fn(async () => []),
}));

jest.mock('../src/features/exportPrep/exportStaging', () => ({
  stagingFileExists: jest.fn(),
}));

jest.mock('../src/features/exportPrep/stagedSha256', () => ({
  hashStagedFileSha256Hex: jest.fn(),
  hashStagedFileSha256Detailed: jest.fn(),
  classifyStagedDigestError: jest.fn((error: unknown) => {
    if (error instanceof DigestCapabilityError) {
      return {
        failure: 'STAGING_DIGEST_UNAVAILABLE' as const,
        code: error.code,
        reason: 'digest_capability_unavailable',
      };
    }
    if (error instanceof DigestIoError) {
      return {
        failure: 'STAGING_DIGEST_FAILED' as const,
        code: error.code,
        reason: 'digest_io_failed',
      };
    }
    return {
      failure: 'STAGING_DIGEST_FAILED' as const,
      code: 'EXPORT_PREP_HASH_FAILED',
      reason: 'digest_io_failed',
    };
  }),
}));

const SHA = 'c'.repeat(64);
const OTHER_SHA = 'd'.repeat(64);

function readyJob() {
  return {
    staging_uri: 'file:///docs/export-staging/s1/0001_p1.jpg',
    export_file_name: '0001_p1.jpg',
    size_bytes: 12,
    sha256: SHA,
    ready_at: '2026-01-01T00:00:00.000Z',
  };
}

describe('phase3b light/strong integrity', () => {
  beforeEach(() => {
    const { stagingFileExists } = jest.requireMock(
      '../src/features/exportPrep/exportStaging',
    ) as { stagingFileExists: jest.Mock };
    const FileSystem = jest.requireMock('expo-file-system') as {
      getInfoAsync: jest.Mock;
    };
    const { hashStagedFileSha256Hex } = jest.requireMock(
      '../src/features/exportPrep/stagedSha256',
    ) as { hashStagedFileSha256Hex: jest.Mock };

    stagingFileExists.mockReset();
    FileSystem.getInfoAsync.mockReset();
    hashStagedFileSha256Hex.mockReset();

    stagingFileExists.mockResolvedValue(true);
    FileSystem.getInfoAsync.mockResolvedValue({ exists: true, size: 12 });
    hashStagedFileSha256Hex.mockResolvedValue(SHA);
  });

  test('light ok then strong detects same-size SHA mismatch', async () => {
    const { hashStagedFileSha256Hex } = jest.requireMock(
      '../src/features/exportPrep/stagedSha256',
    ) as { hashStagedFileSha256Hex: jest.Mock };
    hashStagedFileSha256Hex.mockResolvedValue(OTHER_SHA);

    const light = await validateReadyStaging(readyJob(), 'light');
    expect(light.ok).toBe(true);
    expect(hashStagedFileSha256Hex).not.toHaveBeenCalled();

    const strong = await validateReadyStaging(readyJob(), 'strong');
    expect(strong.ok).toBe(false);
    expect(strong.failure).toBe('STAGING_SHA_MISMATCH');
    expect(strong.actualSha256).toBe(OTHER_SHA);
    expect(isConfirmedReadyIntegrityFailure(strong.failure)).toBe(true);
  });

  test('light ok then file missing → STAGING_FILE_MISSING', async () => {
    const { stagingFileExists } = jest.requireMock(
      '../src/features/exportPrep/exportStaging',
    ) as { stagingFileExists: jest.Mock };
    const FileSystem = jest.requireMock('expo-file-system') as {
      getInfoAsync: jest.Mock;
    };

    stagingFileExists.mockResolvedValueOnce(true);
    const light = await validateReadyStaging(readyJob(), 'light');
    expect(light.ok).toBe(true);

    stagingFileExists.mockResolvedValueOnce(false);
    FileSystem.getInfoAsync.mockResolvedValueOnce({ exists: false });
    const strong = await validateReadyStaging(readyJob(), 'strong');
    expect(strong.ok).toBe(false);
    expect(strong.failure).toBe('STAGING_FILE_MISSING');
    expect(isConfirmedReadyIntegrityFailure(strong.failure)).toBe(true);
  });

  test('DigestCapabilityError → STAGING_DIGEST_UNAVAILABLE (not confirmed)', async () => {
    const { hashStagedFileSha256Hex } = jest.requireMock(
      '../src/features/exportPrep/stagedSha256',
    ) as { hashStagedFileSha256Hex: jest.Mock };
    hashStagedFileSha256Hex.mockRejectedValue(
      new DigestCapabilityError('digestFile unavailable'),
    );

    const result = await validateReadyStaging(readyJob(), 'strong');
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_DIGEST_UNAVAILABLE');
    expect(isConfirmedReadyIntegrityFailure(result.failure)).toBe(false);
  });

  test('DigestIoError → STAGING_DIGEST_FAILED (not confirmed)', async () => {
    const { hashStagedFileSha256Hex } = jest.requireMock(
      '../src/features/exportPrep/stagedSha256',
    ) as { hashStagedFileSha256Hex: jest.Mock };
    hashStagedFileSha256Hex.mockRejectedValue(new DigestIoError('EIO'));

    const result = await validateReadyStaging(readyJob(), 'strong');
    expect(result.ok).toBe(false);
    expect(result.failure).toBe('STAGING_DIGEST_FAILED');
    expect(isConfirmedReadyIntegrityFailure(result.failure)).toBe(false);
  });
});
