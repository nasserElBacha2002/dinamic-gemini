import {
  CaptureService,
  OtherAisleCaptureActiveError,
  type CaptureMediaStore,
  type CaptureSnapshot,
  type CaptureStabilityProber,
} from '../src/features/capture/captureService';
import { createLogger } from '../src/core/logging';
import { collectNewSinceFloor } from '../src/core/incrementalScan';
import { EMPTY_CURSOR, type CompositeCursor } from '../src/core/compositeCursor';
import type { GalleryImage } from '../src/domain/entities/galleryImage';
import type { CapturePhotoStatus, CaptureSessionStatus } from '../src/domain/enums/photoStatus';
import type { CaptureRepository, CreateCaptureSessionInput, CreateCaptureSessionResult, StabilityResultInput } from '../src/database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../src/database/schema/captureSchema';
import type { ForegroundService } from '../src/native/foregroundService';

const image: GalleryImage = {
  assetId: '100',
  mediaStoreNumericId: 100,
  uri: 'file://photo.jpg',
  displayName: 'photo.jpg',
  mimeType: 'image/jpeg',
  size: 1000,
  width: 10,
  height: 10,
  dateAdded: 10,
  dateModified: 10,
  bucketId: null,
  relativePath: null,
};

function session(overrides: Partial<CaptureSessionRow> = {}): CaptureSessionRow {
  const now = '2026-01-01T00:00:00Z';
  return {
    id: 'session-1',
    inventory_id: 'inv-1',
    inventory_name: 'Inventario',
    aisle_id: 'aisle-1',
    aisle_name: 'A1',
    status: 'paused',
    started_at: now,
    finished_at: null,
    initial_asset_id: null,
    initial_date_added: null,
    initial_date_modified: null,
    initial_display_name: null,
    initial_size: null,
    initial_bucket_id: null,
    scan_cursor_date_added: EMPTY_CURSOR.dateAdded,
    scan_cursor_asset_id: EMPTY_CURSOR.assetId,
    last_valid_cursor_date_added: EMPTY_CURSOR.dateAdded,
    last_valid_cursor_asset_id: EMPTY_CURSOR.assetId,
    upload_batch_id: 'batch-1',
    upload_status: 'idle',
    processing_status: 'idle',
    backend_job_id: null,
    upload_started_at: null,
    upload_completed_at: null,
    processing_started_at: null,
    processing_finished_at: null,
    last_upload_error: null,
    last_processing_error: null,
    preparation_processing_mode: 'UNKNOWN',
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

function photo(status: CapturePhotoStatus): CapturePhotoRow {
  const now = '2026-01-01T00:00:00Z';
  return {
    id: 'session-1:100',
    capture_session_id: 'session-1',
    asset_id: image.assetId,
    media_store_numeric_id: image.mediaStoreNumericId ?? null,
    uri: image.uri,
    display_name: image.displayName,
    mime_type: image.mimeType,
    size: image.size,
    width: image.width,
    height: image.height,
    date_added: image.dateAdded,
    date_modified: image.dateModified,
    bucket_id: image.bucketId,
    relative_path: image.relativePath,
    status,
    rejection_reason: null,
    stability_checks: 0,
    stability_attempts: 0,
    stability_error: null,
    last_stability_attempt_at: null,
    detected_at: now,
    stable_at: null,
    excluded_at: null,
    client_file_id: null,
    backend_asset_id: null,
    upload_status: 'not_queued',
    upload_progress: 0,
    upload_attempts: 0,
    upload_batch_id: null,
    last_upload_error_code: null,
    last_upload_error_message: null,
    last_upload_attempt_at: null,
    next_retry_at: null,
    uploaded_at: null,
    remote_deleted_at: null,
    local_transform_uri: null,
    original_size: null,
    upload_size: null,
    created_at: now,
    updated_at: now,
  };
}

class FakeRepo {
  sessions = new Map<string, CaptureSessionRow>();
  photos = new Map<string, CapturePhotoRow>();
  createCalls = 0;

  async createSessionExclusive(input: CreateCaptureSessionInput): Promise<CreateCaptureSessionResult> {
    this.createCalls += 1;
    const existing = await this.findExclusiveCaptureSession();
    if (existing) {
      return { session: existing, created: false };
    }
    const row = session({
      id: input.id,
      inventory_id: input.inventoryId,
      inventory_name: input.inventoryName,
      aisle_id: input.aisleId,
      aisle_name: input.aisleName,
      status: 'preparing',
      upload_batch_id: input.uploadBatchId,
    });
    this.sessions.set(row.id, row);
    return { session: row, created: true };
  }

  async listActivitySessions() {
    return this.listOpenSessions();
  }

  async listOpenSessions() {
    return Array.from(this.sessions.values())
      .filter((s) =>
        [
          'preparing',
          'active',
          'paused',
          'finishing',
          'review',
          'uploading',
          'upload_review',
          'ready_to_process',
          'processing',
          'failed',
          'failed_processing',
        ].includes(s.status),
      )
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }

  async listExclusiveCaptureSessions() {
    return Array.from(this.sessions.values())
      .filter((s) => ['preparing', 'active', 'finishing'].includes(s.status))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }

  async findExclusiveCaptureSession() {
    const [first] = await this.listExclusiveCaptureSessions();
    return first ?? null;
  }

  async findCurrentOpenSession() {
    return this.findExclusiveCaptureSession();
  }

  async repairMultipleOpenSessions(keepId: string) {
    for (const row of this.sessions.values()) {
      if (row.id !== keepId) {
        this.sessions.set(row.id, { ...row, status: 'failed' });
      }
    }
  }

  async getSession(id: string) {
    return this.sessions.get(id) ?? null;
  }

  async updateSessionStatus(id: string, status: CaptureSessionStatus) {
    const row = this.sessions.get(id);
    if (!row) throw new Error('missing session');
    this.sessions.set(id, { ...row, status });
  }

  async listPhotos(sessionId: string) {
    return Array.from(this.photos.values()).filter((p) => p.capture_session_id === sessionId);
  }

  async inspectedAssetIds(sessionId: string) {
    return new Set((await this.listPhotos(sessionId)).map((p) => p.asset_id));
  }

  async updateScanCursor(id: string, cursor: CompositeCursor) {
    const row = this.sessions.get(id);
    if (row) {
      this.sessions.set(id, { ...row, scan_cursor_date_added: cursor.dateAdded, scan_cursor_asset_id: cursor.assetId });
    }
  }

  async updateLastValidCursor(id: string, cursor: CompositeCursor) {
    const row = this.sessions.get(id);
    if (row) {
      this.sessions.set(id, { ...row, last_valid_cursor_date_added: cursor.dateAdded, last_valid_cursor_asset_id: cursor.assetId });
    }
  }

  async upsertPhoto(sessionId: string, img: GalleryImage, status: CapturePhotoStatus) {
    this.photos.set(`${sessionId}:${img.assetId}`, { ...photo(status), capture_session_id: sessionId, asset_id: img.assetId });
  }

  async getPhoto(sessionId: string, assetId: string) {
    return this.photos.get(`${sessionId}:${assetId}`) ?? null;
  }

  async updatePhotoStatus(sessionId: string, assetId: string, status: CapturePhotoStatus) {
    const key = `${sessionId}:${assetId}`;
    const row = this.photos.get(key);
    if (!row) throw new Error('missing photo');
    this.photos.set(key, { ...row, status });
  }

  async applyStabilityResult(input: StabilityResultInput) {
    const key = `${input.sessionId}:${input.assetId}`;
    const row = this.photos.get(key);
    if (!row || (row.status !== 'detected' && row.status !== 'waiting_stability')) {
      return false;
    }
    this.photos.set(key, {
      ...row,
      status: input.status,
      stability_error: input.error,
      stability_checks: input.checks,
      stability_attempts: row.stability_attempts + 1,
    });
    return true;
  }

  async markValidationInterrupted(sessionId: string, assetId: string, error: 'validation_interrupted' | 'validation_timeout') {
    const key = `${sessionId}:${assetId}`;
    const row = this.photos.get(key);
    if (!row || (row.status !== 'detected' && row.status !== 'waiting_stability')) {
      return false;
    }
    this.photos.set(key, { ...row, status: 'unstable', stability_error: error });
    return true;
  }
}

function foreground(): ForegroundService {
  return {
    isAvailable: true,
    start: jest.fn().mockResolvedValue(undefined),
    update: jest.fn().mockResolvedValue(undefined),
    stop: jest.fn().mockResolvedValue(undefined),
  };
}

function mediaStore(images: GalleryImage[] = []): CaptureMediaStore {
  return {
    queryMostRecentPhoto: jest.fn().mockResolvedValue(null),
    queryNewPhotosSince: jest.fn().mockResolvedValue({
      images,
      metrics: { assetsRead: images.length, pagesQueried: 1, assetsHydrated: images.length, newCandidates: images.length, durationMs: 1 },
    }),
    subscribeToGalleryChanges: jest.fn().mockReturnValue({ remove: jest.fn() }),
    fileExists: jest.fn().mockResolvedValue(true),
  };
}

describe('CaptureService corrections', () => {
  it('rejects starting another aisle while one exclusive capture is active, unless paused first', async () => {
    let id = 0;
    const repo = new FakeRepo();
    const service = new CaptureService(repo as unknown as CaptureRepository, foreground(), createLogger(() => undefined), {
      mediaStore: mediaStore(),
      stabilityProber: { probe: jest.fn().mockResolvedValue({ ok: true, checks: 2 }) },
      createId: () => `session-${++id}`,
    });
    const input = {
      inventoryId: 'inv-1',
      inventoryName: 'Inventario',
      aisleId: 'aisle-1',
      aisleName: 'A1',
      permission: { granted: true, limited: false, canAskAgain: true },
    };

    await service.start(input);
    await expect(service.start({ ...input, aisleId: 'aisle-2', aisleName: 'A2' })).rejects.toBeInstanceOf(
      OtherAisleCaptureActiveError,
    );
    expect((await repo.listExclusiveCaptureSessions()).length).toBe(1);

    await service.start({ ...input, aisleId: 'aisle-2', aisleName: 'A2' }, { pauseOtherAisle: true });
    const exclusive = await repo.listExclusiveCaptureSessions();
    expect(exclusive).toHaveLength(1);
    expect(exclusive[0]?.aisle_id).toBe('aisle-2');
    const paused = (await repo.listActivitySessions()).find((s) => s.aisle_id === 'aisle-1');
    expect(paused?.status).toBe('paused');
  });

  it('restores an interrupted active session as paused with persisted context', async () => {
    const repo = new FakeRepo();
    repo.sessions.set('session-1', session({ status: 'active' }));
    const service = new CaptureService(repo as unknown as CaptureRepository, foreground(), createLogger(() => undefined), {
      mediaStore: mediaStore(),
      stabilityProber: { probe: jest.fn().mockResolvedValue({ ok: true, checks: 2 }) },
    });
    let snapshot: CaptureSnapshot | undefined;
    service.subscribe((s) => {
      snapshot = s;
    });

    await service.restoreLatestOpen();
    const restored = snapshot;

    expect(restored?.session?.status).toBe('paused');
    expect(restored?.context?.inventoryName).toBe('Inventario');
    expect(restored?.warning).toContain('interrumpida');
  });

  it('detects an entire same-second batch anchored to the session floor in one scan', async () => {
    const repo = new FakeRepo();
    // Floor = a photo that existed at session start (id 100 @ second 1000).
    repo.sessions.set(
      'session-1',
      session({ status: 'active', initial_asset_id: '100', initial_date_added: 1000 }),
    );

    // Gallery as MediaStore returns it (newest-first) when 8 drone photos are pulled at once:
    // all share second 2000, tie order does NOT match assetId order, and the floor row (100)
    // shows up in the middle. The legacy early-stop would cut here and miss most of the batch.
    const gallery = [
      { assetId: '105', dateAdded: 2000 },
      { assetId: '108', dateAdded: 2000 },
      { assetId: '101', dateAdded: 2000 },
      { assetId: '107', dateAdded: 2000 },
      { assetId: '100', dateAdded: 1000 },
      { assetId: '103', dateAdded: 2000 },
      { assetId: '106', dateAdded: 2000 },
      { assetId: '102', dateAdded: 2000 },
      { assetId: '104', dateAdded: 2000 },
      { assetId: '99', dateAdded: 999 },
    ];

    const toImage = (c: { assetId: string; dateAdded: number }): GalleryImage => ({
      ...image,
      assetId: c.assetId,
      mediaStoreNumericId: Number(c.assetId),
      uri: `file://photo-${c.assetId}.jpg`,
      displayName: `photo-${c.assetId}.jpg`,
      dateAdded: c.dateAdded,
    });

    const batchMediaStore: CaptureMediaStore = {
      queryMostRecentPhoto: jest.fn().mockResolvedValue(null),
      queryNewPhotosSince: jest.fn(async (opts) => {
        const floor = opts.floorCursor ?? opts.scanCursor;
        const inspected = opts.inspectedAssetIds ?? new Set<string>();
        const res = collectNewSinceFloor(gallery, floor, inspected);
        const images = res.newCandidates.map(toImage);
        return {
          images,
          metrics: {
            assetsRead: res.examined,
            pagesQueried: 1,
            assetsHydrated: images.length,
            newCandidates: images.length,
            durationMs: 1,
          },
        };
      }),
      subscribeToGalleryChanges: jest.fn().mockReturnValue({ remove: jest.fn() }),
      fileExists: jest.fn().mockResolvedValue(true),
    };

    const service = new CaptureService(repo as unknown as CaptureRepository, foreground(), createLogger(() => undefined), {
      mediaStore: batchMediaStore,
      stabilityProber: { probe: jest.fn().mockResolvedValue({ ok: true, checks: 2 }) },
    });

    await service.loadSession('session-1', true);
    await service.requestScan();
    await new Promise((resolve) => setTimeout(resolve, 0));

    const detected = (await repo.listPhotos('session-1')).map((p) => p.asset_id).sort();
    expect(detected).toEqual(['101', '102', '103', '104', '105', '106', '107', '108']);
  });

  it('keeps a photo excluded when stability resolves after exclusion', async () => {
    const repo = new FakeRepo();
    repo.sessions.set('session-1', session({ status: 'paused' }));
    repo.photos.set('session-1:100', photo('waiting_stability'));
    let resolveProbe: ((value: { ok: true; checks: number }) => void) | undefined;
    const prober: CaptureStabilityProber = {
      probe: jest.fn().mockReturnValue(new Promise((resolve) => {
        resolveProbe = resolve;
      })),
    };
    const service = new CaptureService(repo as unknown as CaptureRepository, foreground(), createLogger(() => undefined), {
      mediaStore: mediaStore(),
      stabilityProber: prober,
    });

    await service.loadSession('session-1', false);
    const retry = service.retryErrors();
    await Promise.resolve();
    await service.exclude('100');
    resolveProbe?.({ ok: true, checks: 2 });
    await retry;
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect((await repo.getPhoto('session-1', '100'))?.status).toBe('excluded');
  });
});

