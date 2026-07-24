/**
 * Phase 1 corrections — UploadQueue concurrency, cancel settlement, late success, backpressure.
 */
import { UploadQueue } from '../src/features/upload/uploadQueue';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import { createLogger } from '../src/core/logging';
import { ApiError } from '../src/services/api/apiClient';

jest.mock('../src/features/upload/photoPrepare', () => ({
  preparePhotoForUpload: jest.fn(async (input: { uri: string; size: number }) => ({
    uri: input.uri,
    mimeType: 'image/jpeg',
    size: Math.min(input.size || 1000, 900_000),
    displayName: 'p.jpg',
    transformUri: `file://transform/${encodeURIComponent(input.uri)}.jpg`,
    originalSize: input.size || 1000,
    convertedFromHeic: false,
    preparedWidth: 2000,
    preparedHeight: 1500,
    transformationProfile: 'passthrough',
    preparationProfileId: 'unknown_safe_v1',
    preparationProfileVersion: 2,
    resizeApplied: false,
    reencodeApplied: false,
    formatConversionApplied: false,
    resizeReason: 'none',
    qualityApplied: null,
  })),
  cleanupTransformUri: jest.fn(async () => undefined),
  PrepareFileTooLargeError: class PrepareFileTooLargeError extends Error {
    readonly code = 'PREPARE_FILE_TOO_LARGE';
  },
}));

import { cleanupTransformUri } from '../src/features/upload/photoPrepare';

function session(id: string, overrides: Partial<CaptureSessionRow> = {}): CaptureSessionRow {
  return {
    id,
    inventory_id: 'inv',
    inventory_name: 'Inv',
    aisle_id: 'aisle',
    aisle_name: 'A1',
    status: 'uploading',
    started_at: new Date().toISOString(),
    finished_at: null,
    initial_asset_id: null,
    initial_date_added: null,
    initial_date_modified: null,
    initial_display_name: null,
    initial_size: null,
    initial_bucket_id: null,
    scan_cursor_date_added: 0,
    scan_cursor_asset_id: '',
    last_valid_cursor_date_added: 0,
    last_valid_cursor_asset_id: '',
    upload_batch_id: `batch-${id}`,
    upload_status: 'uploading',
    processing_status: 'idle',
    backend_job_id: null,
    upload_started_at: null,
    upload_completed_at: null,
    processing_started_at: null,
    processing_finished_at: null,
    last_upload_error: null,
    last_processing_error: null,
    preparation_processing_mode: 'UNKNOWN',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

function photo(
  id: string,
  sessionId: string,
  overrides: Partial<CapturePhotoRow> = {},
): CapturePhotoRow {
  return {
    id,
    capture_session_id: sessionId,
    asset_id: `asset-${id}`,
    media_store_numeric_id: null,
    uri: `file://orig/${id}.jpg`,
    display_name: `${id}.jpg`,
    mime_type: 'image/jpeg',
    size: 2_000_000,
    width: 4000,
    height: 3000,
    date_added: 1,
    date_modified: 1,
    bucket_id: null,
    relative_path: null,
    status: 'stable',
    rejection_reason: null,
    stability_checks: 3,
    stability_attempts: 3,
    stability_error: null,
    last_stability_attempt_at: null,
    detected_at: null,
    stable_at: new Date().toISOString(),
    excluded_at: null,
    client_file_id: `cf-${id}`,
    backend_asset_id: null,
    upload_status: 'queued',
    upload_progress: 0,
    upload_attempts: 0,
    upload_batch_id: `batch-${sessionId}`,
    last_upload_error_code: null,
    last_upload_error_message: null,
    last_upload_attempt_at: null,
    next_retry_at: null,
    uploaded_at: null,
    remote_deleted_at: null,
    local_transform_uri: `file://transform/${id}.jpg`,
    original_size: 2_000_000,
    upload_size: 900_000,
    upload_worker_owner: null,
    upload_lease_token: null,
    upload_lease_expires_at: null,
    upload_heartbeat_at: null,
    upload_cancel_requested: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('UploadQueue phase1 corrections', () => {
  const logger = createLogger(() => undefined);

  function buildHarness(input: {
    sessions: CaptureSessionRow[];
    photosBySession: Record<string, CapturePhotoRow[]>;
    uploadBatch?: jest.Mock;
    deleteAsset?: jest.Mock;
    ensureLoadedDelayMs?: number;
    concurrency?: number;
  }) {
    const photos = new Map<string, CapturePhotoRow>();
    for (const list of Object.values(input.photosBySession)) {
      for (const p of list) {
        photos.set(p.id, { ...p });
      }
    }
    const sessions = new Map(input.sessions.map((s) => [s.id, { ...s }]));

    const repo = {
      listActivitySessions: jest.fn(async () => [...sessions.values()]),
      listPhotosForUpload: jest.fn(async (sessionId: string) =>
        [...photos.values()].filter((p) => p.capture_session_id === sessionId),
      ),
      listPhotos: jest.fn(async (sessionId: string) =>
        [...photos.values()].filter((p) => p.capture_session_id === sessionId),
      ),
      getPhotoById: jest.fn(async (id: string) => photos.get(id) ?? null),
      getSession: jest.fn(async (id: string) => sessions.get(id) ?? null),
      setPhotoUploadStatus: jest.fn(
        async (photoId: string, status: CapturePhotoRow['upload_status'], patch: Record<string, unknown> = {}) => {
          const current = photos.get(photoId);
          if (!current) return;
          photos.set(photoId, {
            ...current,
            upload_status: status,
            upload_progress: (patch.progress as number | undefined) ?? current.upload_progress,
            backend_asset_id:
              patch.backendAssetId !== undefined
                ? (patch.backendAssetId as string | null)
                : current.backend_asset_id,
            local_transform_uri:
              patch.localTransformUri !== undefined
                ? (patch.localTransformUri as string | null)
                : current.local_transform_uri,
            upload_size:
              patch.uploadSize !== undefined ? (patch.uploadSize as number | null) : current.upload_size,
            original_size:
              patch.originalSize !== undefined
                ? (patch.originalSize as number | null)
                : current.original_size,
            last_upload_error_code:
              patch.errorCode !== undefined
                ? (patch.errorCode as string | null)
                : current.last_upload_error_code,
            last_upload_error_message:
              patch.errorMessage !== undefined
                ? (patch.errorMessage as string | null)
                : current.last_upload_error_message,
            next_retry_at:
              patch.nextRetryAt !== undefined
                ? (patch.nextRetryAt as string | null)
                : current.next_retry_at,
            upload_attempts: patch.incrementAttempts
              ? current.upload_attempts + 1
              : current.upload_attempts,
            uploaded_at:
              patch.uploadedAt !== undefined ? (patch.uploadedAt as string | null) : current.uploaded_at,
            remote_deleted_at:
              patch.remoteDeletedAt !== undefined
                ? (patch.remoteDeletedAt as string | null)
                : current.remote_deleted_at,
          });
        },
      ),
      setPreparationProcessingMode: jest.fn(async (sessionId: string, mode: string) => {
        const s = sessions.get(sessionId);
        if (s) {
          sessions.set(sessionId, { ...s, preparation_processing_mode: mode });
        }
      }),
      tryAcquireUploadLease: jest.fn(async () => true),
      heartbeatUploadLease: jest.fn(async () => true),
      releaseUploadLease: jest.fn(async () => undefined),
      setUploadCancelRequested: jest.fn(async (photoId: string, requested: boolean) => {
        const current = photos.get(photoId);
        if (current) {
          photos.set(photoId, { ...current, upload_cancel_requested: requested ? 1 : 0 });
        }
      }),
      updateSessionStatus: jest.fn(async () => undefined),
      updateSessionUploadMeta: jest.fn(async () => undefined),
      listStableNotQueued: jest.fn(async () => []),
      ensureClientFileId: jest.fn(async (_s: string, _a: string, id: string) => id),
    };

    let activeUploads = 0;
    let peakUploads = 0;
    const uploadBatch =
      input.uploadBatch ??
      jest.fn(async () => {
        activeUploads += 1;
        peakUploads = Math.max(peakUploads, activeUploads);
        await new Promise((r) => setTimeout(r, 30));
        activeUploads -= 1;
        return { uploaded: [], errors: [] };
      });

    const assetsApi = {
      uploadBatch,
      deleteAsset: input.deleteAsset ?? jest.fn(async () => undefined),
    };

    const limits = {
      ensureLoaded: jest.fn(async () => {
        if (input.ensureLoadedDelayMs) {
          await new Promise((r) => setTimeout(r, input.ensureLoadedDelayMs));
        }
        return {
          max_files_per_request: 10,
          max_request_size_bytes: 50_000_000,
          max_file_size_bytes: 12_000_000,
          upload_batch_concurrency: input.concurrency ?? 2,
          retry_attempts: 5,
          retry_base_delay_ms: 1000,
        };
      }),
      refresh: jest.fn(async () => undefined),
    };

    const connectivity = {
      getState: () => 'online' as const,
      isOnline: () => true,
      isCellular: () => false,
      getSnapshot: () => ({
        state: 'online' as const,
        isConnected: true,
        isInternetReachable: true,
        connectionType: 'wifi',
        isCellular: false,
      }),
      subscribe: () => () => undefined,
    };

    const queue = new UploadQueue(
      repo as never,
      assetsApi as never,
      limits as never,
      connectivity as never,
      logger,
      {
        flags: {
          allowMobileDataUploads: true,
          heicConvertToJpeg: true,
          workManagerScheduling: false,
          advancedReconciliation: true,
          backgroundJobPolling: true,
          aisleDeviceLock: false,
          uploadObservabilityEnabled: false,
          uploadDimensionCap: true,
          uploadAdaptiveQuality: true,
          uploadAdaptiveConcurrency: true,
          uploadAbortEnabled: true,
          backgroundUploadWorker: false,
          backgroundUploadForegroundService: false,
          backgroundUploadRebootResume: false,
        },
      },
    );

    return { queue, repo, photos, sessions, uploadBatch, assetsApi, peakUploads: () => peakUploads };
  }

  it('respects concurrency with delayed ensureLoaded across sessions', async () => {
    const s1 = session('s1');
    const s2 = session('s2');
    const s3 = session('s3');
    const { queue, peakUploads } = buildHarness({
      sessions: [s1, s2, s3],
      photosBySession: {
        s1: [photo('p1', 's1')],
        s2: [photo('p2', 's2')],
        s3: [photo('p3', 's3')],
      },
      concurrency: 2,
      ensureLoadedDelayMs: 5,
    });

    const tick = () => (queue as unknown as { tick: () => Promise<void> }).tick();
    await Promise.all([tick(), tick(), tick()]);
    await new Promise((r) => setTimeout(r, 80));
    expect(peakUploads()).toBeLessThanOrEqual(2);
    expect(queue.getSnapshot().activeRequests).toBeLessThanOrEqual(2);
    await queue.dispose();
  });

  it('does not delete transform while batch is in flight on cancel', async () => {
    (cleanupTransformUri as jest.Mock).mockClear();
    let resolveUpload: (value: unknown) => void = () => undefined;
    const uploadPromise = new Promise((resolve) => {
      resolveUpload = resolve;
    });
    const s1 = session('s1');
    const p1 = photo('p1', 's1');
    const { queue, photos } = buildHarness({
      sessions: [s1],
      photosBySession: { s1: [p1] },
      concurrency: 1,
      uploadBatch: jest.fn(async () => {
        await uploadPromise;
        return {
          uploaded: [{ client_file_id: 'cf-p1', asset_id: 'remote-1' }],
          errors: [],
        };
      }),
    });

    const tick = () => (queue as unknown as { tick: () => Promise<void> }).tick();
    const uploadRun = tick();
    await new Promise((r) => setTimeout(r, 20));
    expect(photos.get('p1')?.upload_status).toBe('uploading');

    await queue.cancelPhoto('p1');
    expect(photos.get('p1')?.upload_status).toBe('excluded');
    expect(cleanupTransformUri).not.toHaveBeenCalled();

    resolveUpload({});
    await uploadRun;
    await new Promise((r) => setTimeout(r, 20));
    expect(cleanupTransformUri).toHaveBeenCalled();
    expect(photos.get('p1')?.upload_status).not.toBe('uploaded');
    await queue.dispose();
  });

  it('reconciles late success after cancel without promoting to uploaded', async () => {
    let resolveUpload: (value: unknown) => void = () => undefined;
    const uploadPromise = new Promise((resolve) => {
      resolveUpload = resolve;
    });
    const deleteAsset = jest.fn(async () => undefined);
    const s1 = session('s1');
    const { queue, photos } = buildHarness({
      sessions: [s1],
      photosBySession: { s1: [photo('p1', 's1'), photo('p2', 's1')] },
      concurrency: 1,
      deleteAsset,
      uploadBatch: jest.fn(async () => {
        await uploadPromise;
        return {
          uploaded: [
            { client_file_id: 'cf-p1', asset_id: 'remote-1' },
            { client_file_id: 'cf-p2', asset_id: 'remote-2' },
          ],
          errors: [],
        };
      }),
    });

    const tick = () => (queue as unknown as { tick: () => Promise<void> }).tick();
    const run = tick();
    await new Promise((r) => setTimeout(r, 20));
    await queue.cancelPhoto('p1');
    resolveUpload({});
    await run;
    await new Promise((r) => setTimeout(r, 20));

    expect(photos.get('p1')?.upload_status).toBe('remote_deleted');
    expect(photos.get('p1')?.backend_asset_id).toBe('remote-1');
    expect(photos.get('p2')?.upload_status).toBe('uploaded');
    expect(deleteAsset).toHaveBeenCalledWith('inv', 'aisle', 'remote-1');
    await queue.dispose();
  });

  it('keeps remote_delete_pending when remote delete fails after cancel', async () => {
    let resolveUpload: (value: unknown) => void = () => undefined;
    const uploadPromise = new Promise((resolve) => {
      resolveUpload = resolve;
    });
    const s1 = session('s1');
    const { queue, photos } = buildHarness({
      sessions: [s1],
      photosBySession: { s1: [photo('p1', 's1')] },
      concurrency: 1,
      deleteAsset: jest.fn(async () => {
        throw new ApiError('fail', 500, 'DELETE_FAILED');
      }),
      uploadBatch: jest.fn(async () => {
        await uploadPromise;
        return {
          uploaded: [{ client_file_id: 'cf-p1', asset_id: 'remote-1' }],
          errors: [],
        };
      }),
    });

    const tick = () => (queue as unknown as { tick: () => Promise<void> }).tick();
    const run = tick();
    await new Promise((r) => setTimeout(r, 20));
    await queue.cancelPhoto('p1');
    resolveUpload({});
    await run;
    await new Promise((r) => setTimeout(r, 20));

    expect(photos.get('p1')?.upload_status).toBe('remote_delete_pending');
    expect(photos.get('p1')?.backend_asset_id).toBe('remote-1');
    await queue.dispose();
  });

  it('applies prepare backpressure while uploads are blocked', async () => {
    const s1 = session('s1');
    const many = Array.from({ length: 40 }, (_, i) =>
      photo(`p${i}`, 's1', {
        local_transform_uri: null,
        upload_size: null,
        size: 1_000_000,
      }),
    );
    let resolveUpload: (value: unknown) => void = () => undefined;
    const uploadPromise = new Promise((resolve) => {
      resolveUpload = resolve;
    });
    const { queue, photos } = buildHarness({
      sessions: [s1],
      photosBySession: { s1: many },
      concurrency: 1,
      uploadBatch: jest.fn(async () => {
        await uploadPromise;
        return { uploaded: [], errors: [] };
      }),
    });

    const tick = () => (queue as unknown as { tick: () => Promise<void> }).tick();
    // Several ticks while upload holds the only slot.
    await tick();
    await new Promise((r) => setTimeout(r, 15));
    await tick();
    await tick();
    await tick();
    await tick();

    const prepared = [...photos.values()].filter((p) => p.upload_size != null && p.upload_size > 0);
    expect(prepared.length).toBeLessThanOrEqual(12);
    resolveUpload({});
    await new Promise((r) => setTimeout(r, 40));
    await queue.dispose();
  });

  it('persists preparation mode per session', async () => {
    const s1 = session('s1', { preparation_processing_mode: 'UNKNOWN' });
    const { queue, sessions, repo } = buildHarness({
      sessions: [s1],
      photosBySession: { s1: [] },
    });
    await queue.setSessionPreparationMode('s1', 'INTERNAL_OCR');
    expect(repo.setPreparationProcessingMode).toHaveBeenCalledWith('s1', 'INTERNAL_OCR');
    expect(sessions.get('s1')?.preparation_processing_mode).toBe('INTERNAL_OCR');
    await queue.dispose();
  });
});
