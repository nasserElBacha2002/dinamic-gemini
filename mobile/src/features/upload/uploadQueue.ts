import { buildMicroBatch } from '../../core/uploadBatching';
import { computeRetryDelayMs } from '../../core/uploadBackoff';
import { classifyUploadHttpError, isSoftPerFileRetryable } from '../../core/uploadErrors';
import type { FeatureFlags } from '../../core/featureFlags';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { BackgroundWorkScheduler } from '../../native/backgroundWork';
import { ApiError } from '../../services/api/apiClient';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import { createId } from '../../shared/createId';
import type { AisleAssetsApi } from './aisleAssetsApi';
import { cleanupTransformUri, preparePhotoForUpload } from './photoPrepare';
import type { UploadLimitsService } from './uploadLimitsService';

export interface UploadQueueOptions {
  readonly flags?: FeatureFlags;
  readonly backgroundWork?: BackgroundWorkScheduler | null;
}

export interface UploadQueueSnapshot {
  readonly pauseReason: string | null;
  readonly activeRequests: number;
  readonly sessions: readonly UploadSessionProgress[];
}

export interface UploadSessionProgress {
  readonly sessionId: string;
  readonly inventoryName: string;
  readonly aisleName: string;
  readonly totalStable: number;
  readonly uploaded: number;
  readonly pending: number;
  readonly uploading: number;
  readonly retryable: number;
  readonly permanent: number;
  readonly excluded: number;
}

export type UploadQueueListener = (snapshot: UploadQueueSnapshot) => void;

export class UploadQueue {
  private pauseReason: string | null = null;
  private activeRequests = 0;
  private disposed = false;
  private tickTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly listeners = new Set<UploadQueueListener>();
  private readonly inFlightPhotos = new Set<string>();
  private connectivityUnsub: (() => void) | null = null;
  private cachedSessions: UploadSessionProgress[] = [];

  constructor(
    private readonly repo: CaptureRepository,
    private readonly assetsApi: AisleAssetsApi,
    private readonly limits: UploadLimitsService,
    private readonly connectivity: ConnectivityService,
    private readonly logger: Logger,
    private readonly options: UploadQueueOptions = {},
  ) {}

  subscribe(listener: UploadQueueListener): () => void {
    this.listeners.add(listener);
    listener(this.getSnapshot());
    return () => this.listeners.delete(listener);
  }

  getSnapshot(): UploadQueueSnapshot {
    return {
      pauseReason: this.pauseReason,
      activeRequests: this.activeRequests,
      sessions: this.cachedSessions,
    };
  }

  async restoreAndStart(): Promise<void> {
    this.connectivityUnsub = this.connectivity.subscribe((state) => {
      if (state === 'offline') {
        void this.pause('offline');
      } else if (state === 'online' && (this.pauseReason === 'offline' || this.pauseReason === 'mobile_data')) {
        void this.applyNetworkPolicyAndMaybeResume();
      }
    });
    await this.limits.ensureLoaded();
    const sessions = await this.repo.listActivitySessions();
    for (const session of sessions) {
      if (['active', 'paused', 'finishing', 'review', 'uploading', 'upload_review'].includes(session.status)) {
        await this.enqueueSession(session.id);
        if (this.options.backgroundWork) {
          void this.options.backgroundWork.scheduleUploadSession(session.id);
        }
      }
    }
    await this.applyNetworkPolicyAndMaybeResume();
    this.scheduleTick(0);
  }

  async enqueueSession(sessionId: string): Promise<void> {
    const notQueued = await this.repo.listStableNotQueued(sessionId);
    for (const photo of notQueued) {
      await this.enqueuePhoto(sessionId, photo.id);
    }
    const session = await this.repo.getSession(sessionId);
    if (session && (session.status === 'review' || session.status === 'finishing')) {
      try {
        if (session.status === 'review' || session.status === 'finishing') {
          // finishing already handled; from review move to uploading when queue has work
        }
      } catch {
        // ignore transition races
      }
    }
    if (session && session.status === 'review') {
      try {
        await this.repo.updateSessionStatus(sessionId, 'uploading');
      } catch {
        // may already be uploading
      }
    }
    this.scheduleTick(0);
    this.emit();
  }

  async enqueuePhoto(sessionId: string, photoId: string): Promise<void> {
    const photo = await this.repo.getPhotoById(photoId);
    if (!photo || photo.capture_session_id !== sessionId) {
      return;
    }
    if (photo.status !== 'stable' || photo.upload_status === 'excluded' || photo.upload_status === 'uploaded') {
      return;
    }
    const session = await this.repo.getSession(sessionId);
    if (!session?.upload_batch_id) {
      this.logger.warn('upload_enqueue_missing_batch', { sessionId });
      return;
    }
    await this.repo.ensureClientFileId(sessionId, photo.asset_id, createId(), session.upload_batch_id);
    if (photo.upload_status === 'not_queued' || photo.upload_status === 'retryable_error') {
      await this.repo.setPhotoUploadStatus(photo.id, 'queued', {
        errorCode: null,
        errorMessage: null,
        nextRetryAt: null,
      });
      this.logger.info('photo_enqueued', { sessionId, photoId: photo.id });
    }
    this.scheduleTick(0);
    this.emit();
  }

  async pause(reason: string): Promise<void> {
    this.pauseReason = reason;
    this.logger.info('upload_paused', { reason });
    this.emit();
  }

  async resume(): Promise<void> {
    this.pauseReason = null;
    this.logger.info('upload_resumed', {});
    this.scheduleTick(0);
    this.emit();
  }

  async retryPhoto(photoId: string): Promise<void> {
    const photo = await this.repo.getPhotoById(photoId);
    if (!photo) {
      return;
    }
    await this.repo.setPhotoUploadStatus(photoId, 'queued', {
      errorCode: null,
      errorMessage: null,
      nextRetryAt: null,
    });
    this.scheduleTick(0);
  }

  async retrySession(sessionId: string): Promise<void> {
    const photos = await this.repo.listPhotos(sessionId);
    for (const photo of photos) {
      if (photo.upload_status === 'retryable_error' || photo.upload_status === 'permanent_error') {
        await this.retryPhoto(photo.id);
      }
    }
  }

  async cancelPhoto(photoId: string): Promise<void> {
    const photo = await this.repo.getPhotoById(photoId);
    if (!photo) {
      return;
    }
    if (['not_queued', 'queued', 'preparing', 'retryable_error', 'permanent_error'].includes(photo.upload_status)) {
      await this.repo.setPhotoUploadStatus(photoId, 'excluded');
      await cleanupTransformUri(photo.local_transform_uri);
    }
    this.emit();
  }

  async excludeUploaded(sessionId: string, photoId: string): Promise<{ ok: boolean; reason: string | null }> {
    const photo = await this.repo.getPhotoById(photoId);
    const session = await this.repo.getSession(sessionId);
    if (!photo || !session || !photo.backend_asset_id) {
      return { ok: false, reason: 'Foto no cargada en backend.' };
    }
    await this.repo.setPhotoUploadStatus(photoId, 'remote_delete_pending');
    try {
      await this.assetsApi.deleteAsset(session.inventory_id, session.aisle_id, photo.backend_asset_id);
      await this.repo.setPhotoUploadStatus(photoId, 'remote_deleted', {
        remoteDeletedAt: new Date().toISOString(),
      });
      return { ok: true, reason: null };
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      if (err?.status === 409) {
        await this.repo.setPhotoUploadStatus(photoId, 'uploaded', {
          errorCode: err.code,
          errorMessage: err.message,
        });
        return { ok: false, reason: 'No se puede eliminar: hay un job activo en el pasillo.' };
      }
      await this.repo.setPhotoUploadStatus(photoId, 'uploaded', {
        errorCode: err?.code ?? 'DELETE_FAILED',
        errorMessage: err?.message ?? String(e),
      });
      return { ok: false, reason: 'No se pudo eliminar el asset remoto.' };
    }
  }

  async getSessionProgress(sessionId: string): Promise<UploadSessionProgress | null> {
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      return null;
    }
    const photos = await this.repo.listPhotos(sessionId);
    return summarizeSession(session, photos);
  }

  async refreshSessionReadiness(sessionId: string): Promise<'ready' | 'pending' | 'blocked'> {
    const photos = await this.repo.listPhotos(sessionId);
    const stable = photos.filter((p) => p.status === 'stable');
    const validating = photos.some((p) => p.status === 'detected' || p.status === 'waiting_stability');
    if (validating) {
      return 'pending';
    }
    const pendingUpload = stable.some((p) =>
      ['not_queued', 'queued', 'preparing', 'uploading', 'retryable_error', 'remote_delete_pending'].includes(
        p.upload_status,
      ),
    );
    if (pendingUpload) {
      return 'pending';
    }
    const permanent = stable.some((p) => p.upload_status === 'permanent_error');
    if (permanent) {
      return 'blocked';
    }
    const session = await this.repo.getSession(sessionId);
    if (session && ['uploading', 'upload_review', 'review'].includes(session.status)) {
      try {
        await this.repo.updateSessionStatus(sessionId, 'ready_to_process');
        await this.repo.updateSessionUploadMeta(sessionId, {
          uploadStatus: 'completed',
          uploadCompletedAt: new Date().toISOString(),
        });
      } catch {
        // ignore
      }
    }
    return 'ready';
  }

  async dispose(): Promise<void> {
    this.disposed = true;
    if (this.tickTimer) {
      clearTimeout(this.tickTimer);
    }
    this.connectivityUnsub?.();
    this.listeners.clear();
  }

  private scheduleTick(delayMs: number): void {
    if (this.disposed) {
      return;
    }
    if (this.tickTimer) {
      clearTimeout(this.tickTimer);
    }
    this.tickTimer = setTimeout(() => {
      void this.tick();
    }, delayMs);
  }

  private async applyNetworkPolicyAndMaybeResume(): Promise<void> {
    if (this.connectivity.getState() === 'offline') {
      await this.pause('offline');
      return;
    }
    const allowCellular = this.options.flags?.allowMobileDataUploads !== false;
    if (!allowCellular && this.connectivity.isCellular?.()) {
      await this.pause('mobile_data');
      return;
    }
    if (this.pauseReason === 'offline' || this.pauseReason === 'mobile_data') {
      await this.resume();
    }
  }

  private async tick(): Promise<void> {
    if (this.disposed || this.pauseReason) {
      return;
    }
    if (this.options.flags?.allowMobileDataUploads === false && this.connectivity.isCellular?.()) {
      await this.pause('mobile_data');
      return;
    }
    const limits = await this.limits.ensureLoaded();
    const concurrency = Math.min(2, Math.max(1, limits.upload_batch_concurrency || 2));
    if (this.activeRequests >= concurrency) {
      this.scheduleTick(500);
      return;
    }

    const sessions = await this.repo.listActivitySessions();
    for (const session of sessions) {
      if (this.activeRequests >= concurrency) {
        break;
      }
      if (!session.upload_batch_id) {
        continue;
      }
      const candidates = (await this.repo.listPhotosForUpload(session.id)).filter((p) => {
        if (this.inFlightPhotos.has(p.id)) {
          return false;
        }
        if (p.upload_status === 'retryable_error' && p.next_retry_at) {
          return Date.parse(p.next_retry_at) <= Date.now();
        }
        return p.upload_status === 'queued' || p.upload_status === 'retryable_error';
      });
      const batch = buildMicroBatch(
        candidates.map((p) => ({
          photoId: p.id,
          clientFileId: p.client_file_id ?? p.id,
          sizeBytes: p.upload_size ?? p.size,
          dateAdded: p.date_added,
          assetId: p.asset_id,
        })),
        {
          maxFilesPerRequest: limits.max_files_per_request,
          maxFileSizeBytes: limits.max_file_size_bytes,
          maxRequestSizeBytes: limits.max_request_size_bytes,
        },
      );
      if (!batch) {
        continue;
      }
      void this.runBatch(session, batch.photoIds);
    }
    this.scheduleTick(1000);
  }

  private async runBatch(session: CaptureSessionRow, photoIds: readonly string[]): Promise<void> {
    const limits = await this.limits.ensureLoaded();
    this.activeRequests += 1;
    for (const id of photoIds) {
      this.inFlightPhotos.add(id);
    }
    this.emit();
    try {
      const preparedFiles = [];
      const clientFileIds: string[] = [];
      const photoRows: CapturePhotoRow[] = [];
      for (const photoId of photoIds) {
        const photo = await this.repo.getPhotoById(photoId);
        if (!photo || !photo.client_file_id) {
          continue;
        }
        await this.repo.setPhotoUploadStatus(photoId, 'preparing');
        try {
          const prepared = await preparePhotoForUpload({
            uri: photo.uri,
            mimeType: photo.mime_type,
            displayName: photo.display_name,
            size: photo.size,
            width: photo.width,
            height: photo.height,
            limits: { maxFileSizeBytes: limits.max_file_size_bytes },
          });
          await this.repo.setPhotoUploadStatus(photoId, 'uploading', {
            progress: 0,
            localTransformUri: prepared.transformUri,
            originalSize: prepared.originalSize,
            uploadSize: prepared.size,
            incrementAttempts: true,
          });
          preparedFiles.push({
            uri: prepared.uri,
            name: prepared.displayName,
            mimeType: prepared.mimeType,
          });
          clientFileIds.push(photo.client_file_id);
          photoRows.push(photo);
        } catch (e) {
          await this.repo.setPhotoUploadStatus(photoId, 'permanent_error', {
            errorCode: 'PREPARE_FAILED',
            errorMessage: String(e),
          });
        }
      }
      if (preparedFiles.length === 0) {
        return;
      }
      this.logger.info('upload_started', {
        sessionId: session.id,
        count: preparedFiles.length,
      });
      const response = await this.assetsApi.uploadBatch({
        inventoryId: session.inventory_id,
        aisleId: session.aisle_id,
        uploadBatchId: session.upload_batch_id!,
        clientFileIds,
        files: preparedFiles,
      });
      const byClient = new Map(photoRows.map((p) => [p.client_file_id!, p]));
      for (const ok of response.uploaded ?? []) {
        const photo = ok.client_file_id ? byClient.get(ok.client_file_id) : undefined;
        if (!photo) {
          continue;
        }
        await this.repo.setPhotoUploadStatus(photo.id, 'uploaded', {
          progress: 1,
          backendAssetId: ok.asset_id,
          uploadedAt: new Date().toISOString(),
          errorCode: null,
          errorMessage: null,
          nextRetryAt: null,
        });
        await cleanupTransformUri(photo.local_transform_uri);
        this.logger.info('upload_confirmed', { photoId: photo.id, assetId: ok.asset_id });
      }
      for (const err of response.errors ?? []) {
        const photo = err.client_file_id ? byClient.get(err.client_file_id) : undefined;
        if (!photo) {
          continue;
        }
        const retryable = isSoftPerFileRetryable(err.code);
        const attempt = photo.upload_attempts;
        if (retryable && attempt < limits.retry_attempts) {
          const delay = computeRetryDelayMs({
            attempt,
            baseDelayMs: limits.retry_base_delay_ms,
          });
          await this.repo.setPhotoUploadStatus(photo.id, 'retryable_error', {
            errorCode: err.code,
            errorMessage: err.detail,
            nextRetryAt: new Date(Date.now() + delay).toISOString(),
          });
          this.logger.warn('upload_retry', { photoId: photo.id, code: err.code, delay });
        } else {
          await this.repo.setPhotoUploadStatus(photo.id, 'permanent_error', {
            errorCode: err.code,
            errorMessage: err.detail,
          });
        }
      }
      await this.refreshSessionReadiness(session.id);
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      const klass = classifyUploadHttpError(err?.status ?? null, err?.code ?? null);
      if (klass === 'auth') {
        await this.pause('auth');
      } else if (klass === 'retryable') {
        await this.pause('offline');
        // mark photos retryable
        for (const photoId of photoIds) {
          const photo = await this.repo.getPhotoById(photoId);
          if (!photo) {
            continue;
          }
          const delay = computeRetryDelayMs({
            attempt: photo.upload_attempts,
            baseDelayMs: limits.retry_base_delay_ms,
          });
          await this.repo.setPhotoUploadStatus(photoId, 'retryable_error', {
            errorCode: err?.code ?? 'NETWORK_ERROR',
            errorMessage: err?.message ?? String(e),
            nextRetryAt: new Date(Date.now() + delay).toISOString(),
          });
        }
      } else if (klass === 'payload_too_large') {
        await this.limits.refresh();
        for (const photoId of photoIds) {
          await this.repo.setPhotoUploadStatus(photoId, 'queued', {
            errorCode: err?.code ?? 'UPLOAD_TOO_LARGE',
            errorMessage: err?.message ?? String(e),
          });
        }
      } else if (klass === 'not_found' || klass === 'forbidden' || klass === 'validation') {
        for (const photoId of photoIds) {
          await this.repo.setPhotoUploadStatus(photoId, 'permanent_error', {
            errorCode: err?.code ?? 'UPLOAD_FAILED',
            errorMessage: err?.message ?? String(e),
          });
        }
      } else {
        for (const photoId of photoIds) {
          const photo = await this.repo.getPhotoById(photoId);
          const delay = computeRetryDelayMs({
            attempt: photo?.upload_attempts ?? 0,
            baseDelayMs: limits.retry_base_delay_ms,
          });
          await this.repo.setPhotoUploadStatus(photoId, 'retryable_error', {
            errorCode: err?.code ?? 'UPLOAD_FAILED',
            errorMessage: err?.message ?? String(e),
            nextRetryAt: new Date(Date.now() + delay).toISOString(),
          });
        }
      }
    } finally {
      this.activeRequests -= 1;
      for (const id of photoIds) {
        this.inFlightPhotos.delete(id);
      }
      this.emit();
    }
  }

  private emit(): void {
    void this.refreshCachedSessions().then(() => {
      const snapshot = this.getSnapshot();
      for (const listener of this.listeners) {
        listener(snapshot);
      }
    });
  }

  private async refreshCachedSessions(): Promise<void> {
    try {
      const sessions = await this.repo.listActivitySessions();
      const progress: UploadSessionProgress[] = [];
      for (const session of sessions) {
        const photos = await this.repo.listPhotos(session.id);
        progress.push(summarizeSession(session, photos));
      }
      this.cachedSessions = progress;
    } catch {
      // keep previous cache
    }
  }
}

function summarizeSession(session: CaptureSessionRow, photos: CapturePhotoRow[]): UploadSessionProgress {
  const stable = photos.filter((p) => p.status === 'stable');
  return {
    sessionId: session.id,
    inventoryName: session.inventory_name,
    aisleName: session.aisle_name,
    totalStable: stable.length,
    uploaded: stable.filter((p) => p.upload_status === 'uploaded').length,
    pending: stable.filter((p) =>
      ['not_queued', 'queued', 'preparing'].includes(p.upload_status),
    ).length,
    uploading: stable.filter((p) => p.upload_status === 'uploading').length,
    retryable: stable.filter((p) => p.upload_status === 'retryable_error').length,
    permanent: stable.filter((p) => p.upload_status === 'permanent_error').length,
    excluded: photos.filter((p) => p.status === 'excluded' || p.upload_status === 'excluded' || p.upload_status === 'remote_deleted').length,
  };
}
