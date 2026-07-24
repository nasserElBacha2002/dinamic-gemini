import { ApiError } from '../src/services/api/apiClient';
import { PreliminaryDetectionSyncService } from '../src/features/preliminarySync/preliminaryDetectionSyncService';
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
    created_at: '2026-07-24T12:00:00.000Z',
    updated_at: '2026-07-24T12:00:00.000Z',
    ...over,
  };
}

function createHarness(opts: {
  flags?: FeatureFlags;
  drafts?: LocalDetectionDraftRow[];
  assetId?: string | null;
  upsert?: jest.Mock;
}) {
  const rows = [...(opts.drafts ?? [draft()])];
  const draftsRepo = {
    markPendingForPhotoWhenReady: jest.fn(async () => 1),
    recoverExpiredSyncLeases: jest.fn(async () => 0),
    listDueForSync: jest.fn(async () => rows.filter((r) => r.sync_status === 'PENDING' || r.sync_status === 'RETRY_SCHEDULED')),
    claimSyncLease: jest.fn(async () => true),
    completeSyncSuccess: jest.fn(async () => true),
    completeSyncTerminal: jest.fn(async () => true),
    completeSyncRetry: jest.fn(async () => true),
  };
  const capture = {
    getPhotoById: jest.fn(async () =>
      opts.assetId === null
        ? null
        : {
            id: 'photo-1',
            capture_session_id: 'sess-1',
            client_file_id: 'cf-1',
            backend_asset_id: opts.assetId ?? 'asset-1',
          },
    ),
    getSession: jest.fn(async () => ({
      id: 'sess-1',
      inventory_id: 'inv-1',
      aisle_id: 'aisle-1',
    })),
  };
  const api = {
    upsertDraft: opts.upsert ?? jest.fn(async () => ({
      draft_id: 'draft-1',
      server_preliminary_id: 'server-1',
      status: 'VALIDATED',
      received_at: '2026-07-24T12:00:01.000Z',
      validation_errors: [],
    })),
  };
  const logger = { info: jest.fn(), warn: jest.fn(), error: jest.fn(), debug: jest.fn() };
  const service = new PreliminaryDetectionSyncService({
    flags: opts.flags ?? flags(),
    drafts: draftsRepo as never,
    capture: capture as never,
    api: api as never,
    logger: logger as never,
  });
  return { service, draftsRepo, api, capture };
}

describe('PreliminaryDetectionSyncService', () => {
  it('does nothing when flag is off', async () => {
    const { service, api } = createHarness({ flags: flags({ mobilePreliminaryDetectionSync: false }) });
    const summary = await service.syncPending();
    expect(summary.attempted).toBe(0);
    expect(api.upsertDraft).not.toHaveBeenCalled();
  });

  it('skips when asset is missing', async () => {
    const { service, api, draftsRepo } = createHarness({ assetId: null });
    draftsRepo.listDueForSync.mockResolvedValue([draft()]);
    const summary = await service.syncPending();
    expect(summary.skipped).toBe(1);
    expect(api.upsertDraft).not.toHaveBeenCalled();
  });

  it('syncs successfully', async () => {
    const { service, draftsRepo } = createHarness({});
    const summary = await service.syncPending();
    expect(summary.synced).toBe(1);
    expect(draftsRepo.completeSyncSuccess).toHaveBeenCalled();
  });

  it('maps 422 to REJECTED', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('validation', 422, 'HTTP_422');
    });
    const { service, draftsRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.rejected).toBe(1);
    expect(draftsRepo.completeSyncTerminal).toHaveBeenCalledWith(
      'draft-1',
      expect.any(String),
      'REJECTED',
      'HTTP_422',
      expect.any(String),
    );
  });

  it('maps 409 to CONFLICT', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('conflict', 409, 'HTTP_409');
    });
    const { service, draftsRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.conflicted).toBe(1);
    expect(draftsRepo.completeSyncTerminal).toHaveBeenCalledWith(
      'draft-1',
      expect.any(String),
      'CONFLICT',
      'HTTP_409',
      expect.any(String),
    );
  });

  it('retries on 500', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('server', 500, 'HTTP_500');
    });
    const { service, draftsRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.retried).toBe(1);
    expect(draftsRepo.completeSyncRetry).toHaveBeenCalled();
  });

  it('retries on 404 asset pending', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('asset pending', 404, 'PENDING_ASSET');
    });
    const { service, draftsRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.retried).toBe(1);
    expect(draftsRepo.completeSyncRetry).toHaveBeenCalled();
  });

  it('terminates on 403', async () => {
    const upsert = jest.fn(async () => {
      throw new ApiError('forbidden', 403, 'HTTP_403');
    });
    const { service, draftsRepo } = createHarness({ upsert });
    const summary = await service.syncPending();
    expect(summary.rejected).toBe(1);
    expect(draftsRepo.completeSyncTerminal).toHaveBeenCalledWith(
      'draft-1',
      expect.any(String),
      'FAILED_TERMINAL',
      'HTTP_403',
      expect.any(String),
    );
  });

  it('enqueuePhotoAfterUpload marks pending then syncs when enabled', async () => {
    const { service, draftsRepo } = createHarness({});
    await service.enqueuePhotoAfterUpload('photo-1');
    expect(draftsRepo.markPendingForPhotoWhenReady).toHaveBeenCalledWith('photo-1');
  });
});
