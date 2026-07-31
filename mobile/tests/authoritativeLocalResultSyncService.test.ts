import { ApiError } from '../src/services/api/apiClient';
import {
  AUTH_INGEST_DISABLED,
  AUTH_VALIDATION_FAILED,
  classifyAuthoritativeSyncError,
} from '../src/features/authoritativeLocalResult/authoritativeLocalResultSyncOutcomeClassifier';
import {
  AUTH_SYNC_LEASE_MS,
  AUTH_SYNC_NO_PROGRESS_MIN_DELAY_MS,
  AUTH_SYNC_REQUEST_TIMEOUT_MS,
  AuthoritativeLocalResultSyncService,
} from '../src/features/authoritativeLocalResult/authoritativeLocalResultSyncService';
import type { ConfirmedLocalResultRow } from '../src/database/repositories/confirmedLocalResultRepository';
import type { FeatureFlags } from '../src/core/featureFlags';
import { DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';

function flags(over: Partial<FeatureFlags> = {}): FeatureFlags {
  return { ...DEFAULT_FEATURE_FLAGS, mobileAuthoritativeLocalCodeScan: true, ...over };
}

function confirmed(over: Partial<ConfirmedLocalResultRow> = {}): ConfirmedLocalResultRow {
  return {
    id: 'result-1',
    capture_photo_id: 'photo-1',
    capture_session_id: 'sess-1',
    client_file_id: 'cf-1',
    asset_id: null,
    detected_internal_code: 'ABC',
    detected_quantity: 1,
    confirmed_internal_code: 'ABC',
    confirmed_quantity: 1,
    quantity_status: 'PRESENT',
    source: 'LOCAL_CODE_SCAN',
    detected_symbology: 'QR_CODE',
    parser_version: '1.1.0',
    detector_version: 'mlkit-1',
    prepared_asset_sha256: 'sha256:' + 'a'.repeat(64),
    confirmed_by_user_id: 'user-1',
    confirmed_at: '2026-07-24T12:00:00.000Z',
    sync_status: 'PENDING',
    sync_attempt_count: 0,
    next_retry_at: null,
    sync_last_error_code: null,
    row_version: 1,
    applied_at: null,
    created_at: '2026-07-24T12:00:00.000Z',
    updated_at: '2026-07-24T12:00:01.000Z',
    ...over,
  };
}

function createHarness(opts: {
  flags?: FeatureFlags;
  rows?: ConfirmedLocalResultRow[];
  assetId?: string | null;
  upsert?: jest.Mock;
}) {
  const rows = [...(opts.rows ?? [confirmed()])];
  const confirmedRepo = {
    recoverExpiredSyncLeases: jest.fn(async () => 0),
    listDueForSync: jest.fn(async () =>
      rows.filter((r) => r.sync_status === 'PENDING' || r.sync_status === 'RETRY_SCHEDULED'),
    ),
    claimSyncLease: jest.fn(async () => true),
    completeSyncSuccess: jest.fn(async () => true),
    completeSyncTerminal: jest.fn(async () => true),
    completeSyncRetry: jest.fn(async () => true),
    resetToPending: jest.fn(async () => true),
    getEarliestSyncRetryAt: jest.fn(async () => '2026-07-24T12:01:00.000Z'),
    markNotReady: jest.fn(async () => undefined),
    setAssetIdForPhoto: jest.fn(async () => undefined),
    markPendingForPhotoWhenReady: jest.fn(async () => 1),
  };
  const capture = {
    getPhotoById: jest.fn(async () =>
      opts.assetId === null
        ? { id: 'photo-1', capture_session_id: 'sess-1', client_file_id: 'cf-1', backend_asset_id: null }
        : {
            id: 'photo-1',
            capture_session_id: 'sess-1',
            client_file_id: 'cf-1',
            backend_asset_id: opts.assetId ?? 'asset-1',
          },
    ),
    getSession: jest.fn(async () => ({ id: 'sess-1', inventory_id: 'inv-1', aisle_id: 'aisle-1' })),
  };
  const api = {
    upsertResult:
      opts.upsert ??
      jest.fn(async () => ({
        result_id: 'result-1',
        asset_id: 'asset-1',
        result_version: 1,
        is_current: true,
        supersedes_result_id: null,
        status: 'ACCEPTED',
      })),
  };
  const logger = { info: jest.fn(), warn: jest.fn(), error: jest.fn(), debug: jest.fn() };
  const timers: Array<{ delay: number; fn: () => void }> = [];
  const service = new AuthoritativeLocalResultSyncService({
    flags: opts.flags ?? flags(),
    confirmed: confirmedRepo as never,
    capture: capture as never,
    api: api as never,
    logger: logger as never,
    nowMs: () => Date.parse('2026-07-24T12:00:00.000Z'),
    setTimeoutFn: ((fn: () => void, delay: number) => {
      timers.push({ delay, fn });
      return 1 as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout,
    clearTimeoutFn: (() => undefined) as typeof clearTimeout,
  });
  return { service, confirmedRepo, api, capture, timers };
}

describe('classifyAuthoritativeSyncError', () => {
  it('maps validation and conflict by stable code', () => {
    expect(
      classifyAuthoritativeSyncError({
        status: 422,
        code: AUTH_VALIDATION_FAILED,
        attempt: 1,
        computeDelayMs: () => 1000,
      }).kind,
    ).toBe('rejected');
    expect(
      classifyAuthoritativeSyncError({
        status: 409,
        code: 'AUTHORITATIVE_IDEMPOTENCY_CONFLICT',
        attempt: 1,
        computeDelayMs: () => 1000,
      }).kind,
    ).toBe('conflict');
  });

  it('keeps untyped 404 as endpoint_missing for old backends', () => {
    expect(
      classifyAuthoritativeSyncError({
        status: 404,
        code: null,
        attempt: 1,
        computeDelayMs: () => 1000,
      }).kind,
    ).toBe('endpoint_missing');
    expect(
      classifyAuthoritativeSyncError({
        status: 404,
        code: AUTH_INGEST_DISABLED,
        attempt: 1,
        computeDelayMs: () => 1000,
      }).kind,
    ).toBe('endpoint_missing');
  });

  it('retries 5xx and timeout-like failures', () => {
    expect(
      classifyAuthoritativeSyncError({
        status: 503,
        code: null,
        attempt: 2,
        computeDelayMs: (a) => a * 1000,
      }).kind,
    ).toBe('retry');
    expect(
      classifyAuthoritativeSyncError({
        status: null,
        code: 'NETWORK_ERROR',
        attempt: 1,
        computeDelayMs: () => 2000,
      }).kind,
    ).toBe('retry');
  });
});

describe('AuthoritativeLocalResultSyncService', () => {
  it('keeps lease longer than request timeout', () => {
    expect(AUTH_SYNC_LEASE_MS).toBeGreaterThan(AUTH_SYNC_REQUEST_TIMEOUT_MS);
  });

  it('does nothing when flag is off', async () => {
    const { service, api } = createHarness({
      flags: flags({ mobileAuthoritativeLocalCodeScan: false }),
    });
    const summary = await service.syncPending();
    expect(summary.attempted).toBe(0);
    expect(api.upsertResult).not.toHaveBeenCalled();
  });

  it('syncs successfully', async () => {
    const { service, confirmedRepo } = createHarness({});
    const summary = await service.syncPending();
    expect(summary.synced).toBe(1);
    expect(confirmedRepo.completeSyncSuccess).toHaveBeenCalled();
  });

  it('syncPendingForSession skips other sessions', async () => {
    const other = confirmed({
      id: 'result-other',
      capture_session_id: 'sess-other',
      capture_photo_id: 'photo-other',
    });
    const mine = confirmed({ id: 'result-1', capture_session_id: 'sess-1' });
    const { service, confirmedRepo, api } = createHarness({ rows: [mine, other] });
    confirmedRepo.listDueForSync = jest.fn(async () => [mine, other]);
    const summary = await service.syncPendingForSession('sess-1');
    expect(summary.attempted).toBe(1);
    expect(summary.synced).toBe(1);
    expect(api.upsertResult).toHaveBeenCalledTimes(1);
  });

  it('syncResults only syncs selected ids', async () => {
    const a = confirmed({ id: 'result-a' });
    const b = confirmed({ id: 'result-b', capture_photo_id: 'photo-2' });
    const { service, confirmedRepo, api } = createHarness({ rows: [a, b] });
    confirmedRepo.listDueForSync = jest.fn(async () => [a, b]);
    const summary = await service.syncResults(['result-b']);
    expect(summary.attempted).toBe(1);
    expect(api.upsertResult).toHaveBeenCalledTimes(1);
  });

  it('resets to pending on endpoint 404', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('not found', 404, null);
    });
    const { service, confirmedRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.endpoint_missing).toBe(1);
    expect(confirmedRepo.resetToPending).toHaveBeenCalled();
    expect(confirmedRepo.completeSyncTerminal).not.toHaveBeenCalled();
  });

  it('maps 422 to rejected', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('validation', 422, AUTH_VALIDATION_FAILED);
    });
    const { service, confirmedRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.rejected).toBe(1);
    expect(confirmedRepo.completeSyncTerminal).toHaveBeenCalledWith(
      'result-1',
      'REJECTED',
      AUTH_VALIDATION_FAILED,
      expect.any(String),
    );
  });

  it('marks invalid local results terminal and applies no-progress backoff', async () => {
    const { service, confirmedRepo, api, timers } = createHarness({
      rows: [
        confirmed({
          prepared_asset_sha256: '',
          confirmed_internal_code: 'ABC',
        }),
      ],
    });
    confirmedRepo.getEarliestSyncRetryAt.mockResolvedValue('2026-07-24T12:00:00.000Z');
    const summary = await service.syncPending();
    expect(summary.failed_terminal).toBe(1);
    expect(summary.synced).toBe(0);
    expect(api.upsertResult).not.toHaveBeenCalled();
    expect(confirmedRepo.completeSyncTerminal).toHaveBeenCalledWith(
      'result-1',
      'FAILED_TERMINAL',
      'INVALID_LOCAL_RESULT',
      expect.any(String),
    );
    expect(timers.length).toBeGreaterThanOrEqual(1);
    expect(timers[timers.length - 1]!.delay).toBeGreaterThanOrEqual(AUTH_SYNC_NO_PROGRESS_MIN_DELAY_MS);
  });

  it('stops scheduling after sqlite malformed errors', async () => {
    const { service, confirmedRepo, timers } = createHarness({});
    confirmedRepo.recoverExpiredSyncLeases.mockRejectedValue(
      new Error('database disk image is malformed'),
    );
    await expect(service.syncPending()).rejects.toThrow(/malformed/);
    const timerCountAfter = timers.length;
    confirmedRepo.getEarliestSyncRetryAt.mockResolvedValue('2026-07-24T12:00:00.000Z');
    await service.rescheduleRetryTimer();
    expect(timers.length).toBe(timerCountAfter);
    const empty = await service.syncPending();
    expect(empty.attempted).toBe(0);
  });
});
