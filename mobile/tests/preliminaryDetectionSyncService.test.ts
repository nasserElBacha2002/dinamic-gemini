import { ApiError } from '../src/services/api/apiClient';
import {
  PRELIMINARY_ASSET_PENDING,
  PRELIMINARY_INGEST_DISABLED,
  PRELIMINARY_VALIDATION_FAILED,
  classifyPreliminarySyncError,
} from '../src/features/preliminarySync/preliminarySyncOutcomeClassifier';
import {
  PreliminaryDetectionSyncService,
  SYNC_LEASE_MS,
  SYNC_REQUEST_TIMEOUT_MS,
} from '../src/features/preliminarySync/preliminaryDetectionSyncService';
import type { LocalDetectionDraftRow } from '../src/database/repositories/localDetectionDraftRepository';
import type { FeatureFlags } from '../src/core/featureFlags';
import { DEFAULT_FEATURE_FLAGS } from '../src/core/featureFlags';

function flags(over: Partial<FeatureFlags> = {}): FeatureFlags {
  return { ...DEFAULT_FEATURE_FLAGS, mobilePreliminaryDetectionSync: true, ...over };
}

function draft(over: Partial<LocalDetectionDraftRow> = {}): LocalDetectionDraftRow {
  return {
    id: 'draft-1',
    capture_photo_id: 'photo-1',
    capture_session_id: 'sess-1',
    client_file_id: 'cf-1',
    status: 'RESOLVED',
    raw_value_hash: 'sha256:' + 'b'.repeat(64),
    internal_code: 'ABC',
    quantity: 1,
    quantity_status: 'PRESENT',
    detected_format: 'PIPE',
    detected_symbology: 'QR_CODE',
    parser_version: '1.1.0',
    detector_version: 'mlkit-1',
    candidate_count: 1,
    error_code: null,
    processing_ms: 10,
    comparison_status: null,
    compare_result: null,
    compared_at: null,
    prepared_asset_fingerprint: 'sha256:' + 'a'.repeat(64),
    scan_owner: null,
    scan_generation: 1,
    sync_status: 'PENDING',
    sync_attempt_count: 0,
    sync_next_retry_at: null,
    sync_last_error_code: null,
    server_preliminary_id: null,
    synced_at: null,
    sync_lease_token: null,
    sync_lease_expires_at: null,
    detected_at: '2026-07-24T12:00:00.000Z',
    created_at: '2026-07-24T12:00:00.000Z',
    updated_at: '2026-07-24T12:00:01.000Z',
    ...over,
  };
}

function createHarness(opts: {
  flags?: FeatureFlags;
  drafts?: LocalDetectionDraftRow[];
  assetId?: string | null;
  upsert?: jest.Mock;
  sessionCalls?: { count: number };
}) {
  const rows = [...(opts.drafts ?? [draft()])];
  const sessionCalls = opts.sessionCalls ?? { count: 0 };
  const draftsRepo = {
    markPendingForPhotoWhenReady: jest.fn(async () => 1),
    recoverExpiredSyncLeases: jest.fn(async () => 0),
    listDueForSync: jest.fn(async () =>
      rows.filter((r) => r.sync_status === 'PENDING' || r.sync_status === 'RETRY_SCHEDULED'),
    ),
    claimSyncLease: jest.fn(async () => true),
    completeSyncSuccess: jest.fn(async () => true),
    completeSyncTerminal: jest.fn(async () => true),
    completeSyncRetry: jest.fn(async () => true),
    getEarliestSyncRetryAt: jest.fn(async () => '2026-07-24T12:01:00.000Z'),
    markNotReady: jest.fn(async () => undefined),
    purgeSyncedOlderThan: jest.fn(async () => 0),
    purgeTerminalOlderThan: jest.fn(async () => 0),
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
    getSession: jest.fn(async () => {
      sessionCalls.count += 1;
      return { id: 'sess-1', inventory_id: 'inv-1', aisle_id: 'aisle-1' };
    }),
  };
  const api = {
    upsertDraft:
      opts.upsert ??
      jest.fn(async () => ({
        draft_id: 'draft-1',
        requested_draft_id: 'draft-1',
        server_preliminary_id: 'server-1',
        status: 'VALIDATED',
        received_at: '2026-07-24T12:00:01.000Z',
        validation_errors: [],
      })),
  };
  const logger = { info: jest.fn(), warn: jest.fn(), error: jest.fn(), debug: jest.fn() };
  const timers: Array<{ delay: number; fn: () => void }> = [];
  const service = new PreliminaryDetectionSyncService({
    flags: opts.flags ?? flags(),
    drafts: draftsRepo as never,
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
  return { service, draftsRepo, api, capture, timers, sessionCalls };
}

describe('classifyPreliminarySyncError', () => {
  it('classifies by stable code not message text', () => {
    expect(
      classifyPreliminarySyncError({
        status: 404,
        code: PRELIMINARY_INGEST_DISABLED,
        attempt: 1,
        computeDelayMs: () => 1000,
      }).kind,
    ).toBe('feature_unavailable');
    expect(
      classifyPreliminarySyncError({
        status: 404,
        code: PRELIMINARY_ASSET_PENDING,
        attempt: 1,
        computeDelayMs: () => 1000,
      }).kind,
    ).toBe('pending_asset');
    expect(
      classifyPreliminarySyncError({
        status: 422,
        code: PRELIMINARY_VALIDATION_FAILED,
        attempt: 1,
        computeDelayMs: () => 1000,
      }).kind,
    ).toBe('rejected');
  });
});

describe('PreliminaryDetectionSyncService', () => {
  it('keeps lease longer than request timeout', () => {
    expect(SYNC_LEASE_MS).toBeGreaterThan(SYNC_REQUEST_TIMEOUT_MS);
  });

  it('does nothing when flag is off', async () => {
    const { service, api } = createHarness({
      flags: flags({ mobilePreliminaryDetectionSync: false }),
    });
    const summary = await service.syncPending();
    expect(summary.attempted).toBe(0);
    expect(api.upsertDraft).not.toHaveBeenCalled();
  });

  it('marks NOT_READY_ASSET when asset missing', async () => {
    const { service, draftsRepo, api } = createHarness({ assetId: null });
    const summary = await service.syncPending();
    expect(summary.not_ready).toBe(1);
    expect(draftsRepo.markNotReady).toHaveBeenCalledWith(
      'draft-1',
      'NOT_READY_ASSET',
      expect.any(String),
    );
    expect(api.upsertDraft).not.toHaveBeenCalled();
  });

  it('syncs successfully', async () => {
    const { service, draftsRepo } = createHarness({});
    const summary = await service.syncPending();
    expect(summary.synced).toBe(1);
    expect(draftsRepo.completeSyncSuccess).toHaveBeenCalled();
  });

  it('maps 422 to rejected via code', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('validation', 422, PRELIMINARY_VALIDATION_FAILED);
    });
    const { service, draftsRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.rejected).toBe(1);
    expect(draftsRepo.completeSyncTerminal).toHaveBeenCalled();
  });

  it('counts max attempts as failed_terminal not rejected', async () => {
    const { service, draftsRepo } = createHarness({
      drafts: [draft({ sync_attempt_count: 8 })],
    });
    const summary = await service.syncPending();
    expect(summary.failed_terminal).toBe(1);
    expect(summary.rejected).toBe(0);
    expect(draftsRepo.completeSyncTerminal).toHaveBeenCalledWith(
      'draft-1',
      expect.any(String),
      'FAILED_TERMINAL',
      'SYNC_MAX_ATTEMPTS',
      expect.any(String),
    );
  });

  it('schedules a single retry timer from earliest next_retry_at', async () => {
    const { service, timers, draftsRepo } = createHarness({});
    await service.rescheduleRetryTimer();
    expect(draftsRepo.getEarliestSyncRetryAt).toHaveBeenCalled();
    expect(timers).toHaveLength(1);
    expect(timers[0]!.delay).toBe(60_000);
  });

  it('caches session lookups across drafts in one batch', async () => {
    const sessionCalls = { count: 0 };
    const { service, capture } = createHarness({
      drafts: [
        draft({ id: 'd1', capture_photo_id: 'p1' }),
        draft({ id: 'd2', capture_photo_id: 'p2' }),
      ],
      sessionCalls,
    });
    (capture.getPhotoById as jest.Mock).mockImplementation((id: string) =>
      Promise.resolve({
        id,
        capture_session_id: 'sess-1',
        client_file_id: 'cf-1',
        backend_asset_id: 'asset-1',
      }),
    );
    await service.syncPending();
    expect(sessionCalls.count).toBe(1);
  });

  it('late response with wrong lease does not complete success', async () => {
    const { service, draftsRepo } = createHarness({});
    draftsRepo.completeSyncSuccess.mockResolvedValue(false);
    const summary = await service.syncPending();
    expect(summary.skipped_lease).toBe(1);
  });
});
