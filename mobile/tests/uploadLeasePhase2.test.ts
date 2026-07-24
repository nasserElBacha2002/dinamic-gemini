import {
  UPLOAD_LEASE_TTL_MS,
  UPLOAD_WORKER_OWNER_JS,
  UPLOAD_WORKER_OWNER_NATIVE,
  hasForeignUploadLease,
  isUploadLeaseActive,
  leaseExpiresAtIso,
  uniqueUploadSessionWorkName,
  UNIQUE_UPLOAD_QUEUE_WORK,
} from '../src/core/uploadLease';
import { resolveFeatureFlags } from '../src/core/featureFlags';

describe('uploadLease', () => {
  it('detects active vs expired leases', () => {
    const future = leaseExpiresAtIso(Date.now(), 60_000);
    const past = new Date(Date.now() - 1_000).toISOString();
    expect(isUploadLeaseActive(future)).toBe(true);
    expect(isUploadLeaseActive(past)).toBe(false);
    expect(isUploadLeaseActive(null)).toBe(false);
    expect(UPLOAD_LEASE_TTL_MS).toBeGreaterThan(60_000);
  });

  it('treats native lease as foreign for JS owner', () => {
    expect(
      hasForeignUploadLease({
        workerOwner: UPLOAD_WORKER_OWNER_NATIVE,
        leaseExpiresAt: leaseExpiresAtIso(),
        selfOwner: UPLOAD_WORKER_OWNER_JS,
      }),
    ).toBe(true);
    expect(
      hasForeignUploadLease({
        workerOwner: UPLOAD_WORKER_OWNER_JS,
        leaseExpiresAt: leaseExpiresAtIso(),
        selfOwner: UPLOAD_WORKER_OWNER_JS,
      }),
    ).toBe(false);
    expect(
      hasForeignUploadLease({
        workerOwner: UPLOAD_WORKER_OWNER_NATIVE,
        leaseExpiresAt: new Date(Date.now() - 5_000).toISOString(),
        selfOwner: UPLOAD_WORKER_OWNER_JS,
      }),
    ).toBe(false);
  });

  it('uses unique work name contract', () => {
    expect(UNIQUE_UPLOAD_QUEUE_WORK).toBe('dinamic-upload-queue');
    expect(uniqueUploadSessionWorkName('abc')).toBe('dinamic-upload-session-abc');
  });

  it('exports stable error codes aligned with Kotlin UploadContracts', () => {
    const {
      UPLOAD_CODE_AUTH_REQUIRED,
      UPLOAD_CODE_AUTH_VAULT_UNAVAILABLE,
      UPLOAD_CODE_UPLOAD_REPREPARE_REQUIRED,
      UPLOAD_CODE_REQUEST_TIMEOUT,
      UPLOAD_CODE_REQUEST_CANCELLED,
      UPLOAD_CODE_FILE_MISSING,
      UPLOAD_CODE_TLS_ERROR,
      UPLOAD_CODE_RESPONSE_PARSE_ERROR,
      UPLOAD_MULTIPART_FIELD_BATCH,
      UPLOAD_MULTIPART_FIELD_CLIENT_IDS,
      UPLOAD_MULTIPART_FIELD_FILES,
    } = require('../src/core/uploadLease') as typeof import('../src/core/uploadLease');
    expect(UPLOAD_CODE_AUTH_REQUIRED).toBe('AUTH_REQUIRED');
    expect(UPLOAD_CODE_AUTH_VAULT_UNAVAILABLE).toBe('AUTH_VAULT_UNAVAILABLE');
    expect(UPLOAD_CODE_UPLOAD_REPREPARE_REQUIRED).toBe('UPLOAD_REPREPARE_REQUIRED');
    expect(UPLOAD_CODE_REQUEST_TIMEOUT).toBe('REQUEST_TIMEOUT');
    expect(UPLOAD_CODE_REQUEST_CANCELLED).toBe('REQUEST_CANCELLED');
    expect(UPLOAD_CODE_FILE_MISSING).toBe('FILE_MISSING');
    expect(UPLOAD_CODE_TLS_ERROR).toBe('TLS_ERROR');
    expect(UPLOAD_CODE_RESPONSE_PARSE_ERROR).toBe('RESPONSE_PARSE_ERROR');
    expect(UPLOAD_MULTIPART_FIELD_BATCH).toBe('upload_batch_id');
    expect(UPLOAD_MULTIPART_FIELD_CLIENT_IDS).toBe('client_file_ids');
    expect(UPLOAD_MULTIPART_FIELD_FILES).toBe('files');
  });
});

describe('phase2 background upload flags', () => {
  it('defaults off in production and on in development', () => {
    const prod = resolveFeatureFlags({}, 'production');
    expect(prod.backgroundUploadWorker).toBe(false);
    expect(prod.backgroundUploadForegroundService).toBe(false);
    expect(prod.backgroundUploadRebootResume).toBe(false);

    const dev = resolveFeatureFlags({}, 'development');
    expect(dev.backgroundUploadWorker).toBe(true);
    expect(dev.backgroundUploadForegroundService).toBe(true);
    expect(dev.backgroundUploadRebootResume).toBe(true);
  });

  it('allows independent opt-in in production', () => {
    const flags = resolveFeatureFlags(
      {
        backgroundUploadWorker: '1',
        backgroundUploadForegroundService: false,
        backgroundUploadRebootResume: '1',
      },
      'production',
    );
    expect(flags.backgroundUploadWorker).toBe(true);
    expect(flags.backgroundUploadForegroundService).toBe(false);
    expect(flags.backgroundUploadRebootResume).toBe(true);
  });
});
