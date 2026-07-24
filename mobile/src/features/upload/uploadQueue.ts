import { buildMicroBatch } from '../../core/uploadBatching';
import { computeRetryDelayMs } from '../../core/uploadBackoff';
import { classifyUploadHttpError, isSoftPerFileRetryable } from '../../core/uploadErrors';
import {
  packingBudgetFromServer,
  relaxPackingBudgetAfterSuccess,
  shrinkPackingBudgetAfter413,
  type PackingBudget,
} from '../../core/uploadPackingBudget';
import type { FeatureFlags } from '../../core/featureFlags';
import {
  defaultImagePreparationPolicy,
  normalizePreparationProcessingMode,
} from '../../core/imagePreparationPolicy';
import { hashPayloadFingerprint } from '../../core/payloadFingerprint';
import { defaultUploadConcurrencyPolicy } from '../../core/uploadConcurrencyPolicy';
import { UploadSlotGate, prepareAllowance } from '../../core/uploadSlotGate';
import {
  UPLOAD_WORKER_OWNER_JS,
  hasForeignUploadLease,
  leaseExpiresAtIso,
} from '../../core/uploadLease';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { LocalCodeScanStrategy } from '../localCodeScan/localCodeScanStrategy';
import type { BackgroundWorkScheduler } from '../../native/backgroundWork';
import {
  createMonotonicClock,
  emitObservability,
  networkAttributesFromConnectivity,
  normalizeNetworkType,
  normalizeObservabilityError,
  prepareMetricAttributes,
  photoMarkKey,
  sessionMarkKey,
  batchMarkKey,
  type ObservabilityReporter,
  type TimingMarkStore,
} from '../../observability';
import { ApiError, REQUEST_ABORTED, REQUEST_TIMEOUT } from '../../services/api/apiClient';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import { createId } from '../../shared/createId';
import type { AisleAssetsApi } from './aisleAssetsApi';
import { cleanupTransformUri, preparePhotoForUpload, PrepareFileTooLargeError } from './photoPrepare';
import type { UploadLimitsService } from './uploadLimitsService';

/** Multipart timeout is 120s; reclaim anything still "uploading/preparing" past this. */
const UPLOAD_STALE_MS = 150_000;
/** How many photos to prepare per tick before packing (keeps UI responsive for 20+ captures). */
const PREPARE_PER_TICK = 4;
/** Backpressure: max prepared-but-not-yet-uploaded photos across sessions. */
const MAX_PREPARED_PENDING = 12;

export interface UploadQueueObservability {
  readonly reporter: ObservabilityReporter;
  readonly marks: TimingMarkStore;
}

export interface UploadQueueOptions {
  readonly flags?: FeatureFlags;
  readonly backgroundWork?: BackgroundWorkScheduler | null;
  readonly observability?: UploadQueueObservability | null;
  /** Phase 3 shadow local CODE_SCAN — never blocks upload authority path. */
  readonly localCodeScan?: LocalCodeScanStrategy | null;
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
  private disposed = false;
  private tickTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly listeners = new Set<UploadQueueListener>();
  private readonly inFlightPhotos = new Set<string>();
  private connectivityUnsub: (() => void) | null = null;
  private cachedSessions: UploadSessionProgress[] = [];
  /** Effective packing budget; null until first limits load, then adapted on 413/success. */
  private packingBudget: PackingBudget | null = null;
  private readonly clock = createMonotonicClock();
  private readonly uploadSlots = new UploadSlotGate();
  /** Sessions that already emitted first-upload session metric. */
  private readonly firstUploadEmitted = new Set<string>();
  /** In-flight multipart AbortControllers keyed by attempt id. */
  private readonly uploadAbortByAttempt = new Map<string, AbortController>();
  /** photoId → attemptId for abort lookup. */
  private readonly uploadAttemptByPhoto = new Map<string, string>();
  /** Photos cancelled while a batch was in flight (excluded after abort). */
  private readonly cancelledWhileUploading = new Set<string>();
  /** Transforms deferred until batch settlement. */
  private readonly pendingTransformCleanup = new Set<string>();

  constructor(
    private readonly repo: CaptureRepository,
    private readonly assetsApi: AisleAssetsApi,
    private readonly limits: UploadLimitsService,
    private readonly connectivity: ConnectivityService,
    private readonly logger: Logger,
    private readonly options: UploadQueueOptions = {},
  ) {}

  private get obs(): UploadQueueObservability | null {
    return this.options.observability ?? null;
  }

  private get flags(): FeatureFlags | undefined {
    return this.options.flags;
  }

  get activeRequests(): number {
    return this.uploadSlots.activeCount;
  }

  private tryAcquireUploadSlot(limit: number): boolean {
    if (this.disposed) {
      return false;
    }
    return this.uploadSlots.tryAcquire(limit);
  }

  private releaseUploadSlot(): void {
    this.uploadSlots.release();
  }

  private resolveNetworkType() {
    const snap = this.connectivity.getSnapshot?.();
    return normalizeNetworkType({
      isConnected: snap?.isConnected ?? (this.connectivity.getState() === 'offline' ? false : true),
      type: snap?.connectionType ?? null,
      isCellular: snap?.isCellular ?? this.connectivity.isCellular?.() ?? false,
    });
  }

  private resolveUploadConcurrency(serverConcurrency: number): number {
    return defaultUploadConcurrencyPolicy.resolve({
      networkType: this.resolveNetworkType(),
      serverConcurrency,
      adaptiveConcurrencyEnabled: this.flags?.uploadAdaptiveConcurrency !== false,
    });
  }

  subscribe(listener: UploadQueueListener): () => void {
    this.listeners.add(listener);
    listener(this.getSnapshot());
    return () => this.listeners.delete(listener);
  }

  getSnapshot(): UploadQueueSnapshot {
    return {
      pauseReason: this.pauseReason,
      activeRequests: this.uploadSlots.activeCount,
      sessions: this.cachedSessions,
    };
  }

  /** Persist preparation profile mode for a capture session (from UI preference). */
  async setSessionPreparationMode(sessionId: string, mode: string | null): Promise<void> {
    const normalized = normalizePreparationProcessingMode(mode);
    await this.repo.setPreparationProcessingMode(sessionId, normalized);
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
    await this.syncPackingBudgetFromServer();
    await this.reclaimOrphanedInFlight();
    const sessions = await this.repo.listActivitySessions();
    emitObservability(this.obs?.reporter, {
      name: 'queue.restored',
      attributes: {
        session_count: sessions.length,
        ...networkAttributesFromConnectivity(this.connectivity),
      },
    });
    for (const session of sessions) {
      if (['active', 'paused', 'finishing', 'review', 'uploading', 'upload_review'].includes(session.status)) {
        await this.enqueueSession(session.id);
        if (this.options.backgroundWork) {
          this.scheduleNativeDrain(session.id);
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
    if (session && session.status === 'review') {
      try {
        await this.repo.updateSessionStatus(sessionId, 'uploading');
      } catch {
        // may already be uploading
      }
    }
    this.scheduleTick(0);
    this.emit();
    this.scheduleNativeDrain(sessionId);
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
    const clientFileId = await this.repo.ensureClientFileId(
      sessionId,
      photo.asset_id,
      createId(),
      session.upload_batch_id,
    );
    if (photo.upload_status === 'not_queued' || photo.upload_status === 'retryable_error') {
      await this.repo.setPhotoUploadStatus(photo.id, 'queued', {
        errorCode: null,
        errorMessage: null,
        nextRetryAt: null,
      });
      this.logger.info('photo_enqueued', { sessionId, photoId: photo.id });
      if (this.obs) {
        this.obs.marks.mark(photoMarkKey(sessionId, clientFileId, 'queued'));
        if (!this.obs.marks.get(sessionMarkKey(sessionId, 'created'))) {
          this.obs.marks.mark(sessionMarkKey(sessionId, 'created'));
        }
        emitObservability(this.obs.reporter, {
          name: 'photo.queued',
          sessionId,
          clientFileId,
          batchId: session.upload_batch_id ?? undefined,
          attributes: {
            original_bytes: photo.size > 0 ? photo.size : null,
            original_width: photo.width > 0 ? photo.width : null,
            original_height: photo.height > 0 ? photo.height : null,
            ...networkAttributesFromConnectivity(this.connectivity),
          },
        });
      }
    }
    this.scheduleTick(0);
    this.emit();
    this.scheduleNativeDrain(sessionId);
  }

  async pause(reason: string): Promise<void> {
    this.pauseReason = reason;
    this.logger.info('upload_paused', { reason });
    this.emit();
    if (reason === 'offline' || reason === 'mobile_data') {
      this.scheduleTick(5_000);
    }
  }

  async resume(): Promise<void> {
    this.pauseReason = null;
    this.logger.info('upload_resumed', {});
    await this.reclaimOrphanedInFlight();
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
      if (
        photo.upload_status === 'retryable_error' ||
        photo.upload_status === 'permanent_error' ||
        photo.upload_status === 'preparing' ||
        photo.upload_status === 'uploading'
      ) {
        await this.retryPhoto(photo.id);
      }
    }
    if (this.pauseReason === 'offline' || this.pauseReason === 'mobile_data' || this.pauseReason === 'auth') {
      await this.resume();
    } else {
      this.scheduleTick(0);
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
      this.emit();
      return;
    }
    if (photo.upload_status === 'uploading') {
      // Intent + abort only; do NOT delete transform while multipart may still read it.
      this.cancelledWhileUploading.add(photoId);
      await this.repo.setUploadCancelRequested(photoId, true);
      const attemptId = this.uploadAttemptByPhoto.get(photoId);
      if (this.flags?.uploadAbortEnabled !== false && attemptId) {
        const controller = this.uploadAbortByAttempt.get(attemptId);
        controller?.abort();
        emitObservability(this.obs?.reporter, {
          name: 'photo.upload_aborted',
          sessionId: photo.capture_session_id,
          clientFileId: photo.client_file_id ?? undefined,
          attemptId,
          attributes: {
            upload_error_code: 'UPLOAD_ABORTED',
          },
        });
      }
      await this.repo.setPhotoUploadStatus(photoId, 'excluded');
      if (photo.local_transform_uri) {
        this.pendingTransformCleanup.add(photo.local_transform_uri);
      }
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
    for (const controller of this.uploadAbortByAttempt.values()) {
      controller.abort();
    }
    this.uploadAbortByAttempt.clear();
    this.uploadAttemptByPhoto.clear();
    this.uploadSlots.reset();
  }

  /**
   * After a late success for a cancelled photo: keep excluded / remote_delete_pending,
   * never promote to uploaded; attempt idempotent remote delete.
   */
  private async reconcileCancelledRemoteAsset(
    session: CaptureSessionRow,
    photoId: string,
    assetId: string,
  ): Promise<void> {
    await this.repo.setPhotoUploadStatus(photoId, 'remote_delete_pending', {
      backendAssetId: assetId,
      errorCode: 'UPLOAD_CANCELLED_REMOTE_PENDING',
      errorMessage: 'Asset remoto creado tras cancelación; eliminación pendiente.',
      nextRetryAt: null,
    });
    try {
      await this.assetsApi.deleteAsset(session.inventory_id, session.aisle_id, assetId);
      await this.repo.setPhotoUploadStatus(photoId, 'remote_deleted', {
        remoteDeletedAt: new Date().toISOString(),
        errorCode: null,
        errorMessage: null,
      });
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      // Stay remote_delete_pending — do not flip cancelled photos back to uploaded.
      await this.repo.setPhotoUploadStatus(photoId, 'remote_delete_pending', {
        backendAssetId: assetId,
        errorCode: err?.code ?? 'DELETE_FAILED',
        errorMessage: err?.message ?? String(e),
      });
      this.logger.warn('error', {
        where: 'reconcile_cancelled_remote',
        photoId,
        code: err?.code ?? null,
        status: err?.status ?? null,
      });
    }
  }

  private async flushPendingTransformCleanup(): Promise<void> {
    const uris = [...this.pendingTransformCleanup];
    this.pendingTransformCleanup.clear();
    for (const uri of uris) {
      await cleanupTransformUri(uri);
    }
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

  private async syncPackingBudgetFromServer(): Promise<PackingBudget> {
    const limits = await this.limits.ensureLoaded();
    const server = {
      maxFilesPerRequest: limits.max_files_per_request,
      maxRequestSizeBytes: limits.max_request_size_bytes,
      maxFileSizeBytes: limits.max_file_size_bytes,
    };
    if (!this.packingBudget) {
      this.packingBudget = packingBudgetFromServer(server);
    } else {
      // Cap by current server ceiling without wiping learned shrinks upward incorrectly.
      this.packingBudget = {
        maxFiles: Math.min(this.packingBudget.maxFiles, Math.max(1, server.maxFilesPerRequest)),
        maxRequestBytes: Math.min(this.packingBudget.maxRequestBytes, Math.max(1, server.maxRequestSizeBytes)),
        maxFileBytes: Math.min(
          this.packingBudget.maxFileBytes,
          Math.max(1, Math.min(server.maxFileSizeBytes, server.maxRequestSizeBytes)),
        ),
      };
    }
    return this.packingBudget;
  }

  private async tick(): Promise<void> {
    if (this.disposed) {
      return;
    }
    if (this.pauseReason === 'offline' || this.pauseReason === 'mobile_data') {
      await this.applyNetworkPolicyAndMaybeResume();
      if (this.pauseReason) {
        this.scheduleTick(5_000);
        return;
      }
    } else if (this.pauseReason) {
      return;
    }
    if (this.options.flags?.allowMobileDataUploads === false && this.connectivity.isCellular?.()) {
      await this.pause('mobile_data');
      return;
    }

    await this.reclaimOrphanedInFlight();
    const limits = await this.limits.ensureLoaded();
    const budget = await this.syncPackingBudgetFromServer();
    const configuredConcurrency = Math.max(1, limits.upload_batch_concurrency || 2);
    const concurrency = this.resolveUploadConcurrency(configuredConcurrency);
    if (concurrency <= 0) {
      await this.pause('offline');
      this.scheduleTick(5_000);
      return;
    }

    const sessions = await this.repo.listActivitySessions();
    let startedUpload = false;
    let globalPreparedPending = 0;
    for (const session of sessions) {
      if (!session.upload_batch_id) {
        continue;
      }
      const photos = await this.repo.listPhotosForUpload(session.id);
      globalPreparedPending += photos.filter(
        (p) =>
          p.upload_size != null &&
          p.upload_size > 0 &&
          ['queued', 'preparing', 'uploading', 'retryable_error'].includes(p.upload_status),
      ).length;
    }

    for (const session of sessions) {
      if (!session.upload_batch_id) {
        continue;
      }

      const eligible = (await this.repo.listPhotosForUpload(session.id)).filter((p) => this.isEligible(p));
      if (eligible.length === 0) {
        continue;
      }

      const freeSlots = Math.max(0, concurrency - this.uploadSlots.activeCount);
      const allowance = prepareAllowance({
        preparedPending: globalPreparedPending,
        freeUploadSlots: freeSlots,
        maxFilesPerBatch: budget.maxFiles,
        maxPreparedPending: MAX_PREPARED_PENDING,
      });

      if (allowance > 0) {
        const needPrepare = eligible.filter((p) => !(p.upload_size != null && p.upload_size > 0));
        for (const photo of needPrepare.slice(0, Math.min(PREPARE_PER_TICK, allowance))) {
          if (this.inFlightPhotos.has(photo.id)) {
            continue;
          }
          await this.preparePhoto(photo, budget.maxFileBytes);
          globalPreparedPending += 1;
        }
      }

      if (!this.tryAcquireUploadSlot(concurrency)) {
        continue;
      }

      const prepared = (await this.repo.listPhotosForUpload(session.id))
        .filter((p) => this.isEligible(p))
        .filter((p) => p.upload_size != null && p.upload_size > 0 && !this.inFlightPhotos.has(p.id));

      const batch = buildMicroBatch(
        prepared.map((p) => ({
          photoId: p.id,
          clientFileId: p.client_file_id ?? p.id,
          sizeBytes: p.upload_size ?? 0,
          dateAdded: p.date_added,
          assetId: p.asset_id,
        })),
        {
          maxFilesPerRequest: budget.maxFiles,
          maxFileSizeBytes: budget.maxFileBytes,
          maxRequestSizeBytes: budget.maxRequestBytes,
          requirePositiveSize: true,
        },
      );

      if (!batch) {
        this.releaseUploadSlot();
        const oversized = prepared.filter((p) => (p.upload_size ?? 0) > budget.maxFileBytes);
        for (const photo of oversized.slice(0, PREPARE_PER_TICK)) {
          if (prepareAllowance({
            preparedPending: globalPreparedPending,
            freeUploadSlots: Math.max(0, concurrency - this.uploadSlots.activeCount),
            maxFilesPerBatch: budget.maxFiles,
            maxPreparedPending: MAX_PREPARED_PENDING,
          }) <= 0) {
            break;
          }
          await this.invalidatePreparedSize(photo.id);
          globalPreparedPending = Math.max(0, globalPreparedPending - 1);
          await this.preparePhoto(photo, budget.maxFileBytes);
          globalPreparedPending += 1;
        }
        continue;
      }

      // Slot already acquired; uploadPreparedBatch releases exactly once in finally.
      void this.uploadPreparedBatch(session, batch.photoIds, batch.totalBytes, {
        configuredConcurrency,
        effectiveConcurrency: concurrency,
      });
      startedUpload = true;
      globalPreparedPending = Math.max(0, globalPreparedPending - batch.photoIds.length);
    }

    const uploadsSaturated = this.uploadSlots.activeCount >= concurrency;
    this.scheduleTick(
      startedUpload || uploadsSaturated || needMoreWorkSoon(sessions.length) ? 400 : 1000,
    );
  }

  private isEligible(photo: CapturePhotoRow): boolean {
    if (this.inFlightPhotos.has(photo.id)) {
      return false;
    }
    if (
      hasForeignUploadLease({
        workerOwner: photo.upload_worker_owner,
        leaseExpiresAt: photo.upload_lease_expires_at,
        selfOwner: UPLOAD_WORKER_OWNER_JS,
      })
    ) {
      return false;
    }
    if (photo.upload_cancel_requested === 1) {
      return false;
    }
    if (photo.upload_status === 'retryable_error') {
      if (!photo.next_retry_at) {
        return true;
      }
      return Date.parse(photo.next_retry_at) <= Date.now();
    }
    return photo.upload_status === 'queued';
  }

  private scheduleNativeDrain(_sessionId?: string): void {
    if (this.flags?.backgroundUploadWorker !== true || !this.options.backgroundWork) {
      return;
    }
    // Single unique queue only — do not also schedule per-session workers.
    void this.options.backgroundWork.scheduleUploadQueue?.(false);
  }

  /**
   * Prepare one photo, persist real upload_size + transform, leave status as queued.
   * Packing uses that size; HTTP upload is a separate step.
   */
  private async preparePhoto(photo: CapturePhotoRow, maxFileBytes: number): Promise<void> {
    if (!photo.client_file_id) {
      return;
    }
    this.inFlightPhotos.add(photo.id);
    const sessionId = photo.capture_session_id;
    const clientFileId = photo.client_file_id;
    const queuedWaitMs = this.obs?.marks.takeElapsedMs(photoMarkKey(sessionId, clientFileId, 'queued')) ?? null;
    const prepareStartedAt = this.clock.nowMs();
    const network = networkAttributesFromConnectivity(this.connectivity);
    if (this.obs) {
      this.obs.marks.mark(photoMarkKey(sessionId, clientFileId, 'prepare_started'));
      emitObservability(this.obs.reporter, {
        name: 'photo.prepare_started',
        sessionId,
        clientFileId,
        batchId: photo.upload_batch_id ?? undefined,
        durationMs: queuedWaitMs ?? undefined,
        attributes: {
          queued_to_prepare_started_ms: queuedWaitMs,
          ...network,
        },
      });
    }
    try {
      await this.repo.setPhotoUploadStatus(photo.id, 'preparing', {
        incrementAttempts: true,
      });
      const session = await this.repo.getSession(photo.capture_session_id);
      const mode = normalizePreparationProcessingMode(session?.preparation_processing_mode);
      const profile = defaultImagePreparationPolicy.resolve({
        processingMode: mode,
        networkType: this.resolveNetworkType(),
        serverLimits: { maxFileSizeBytes: maxFileBytes },
        dimensionCapEnabled: this.flags?.uploadDimensionCap !== false,
        adaptiveQualityEnabled: this.flags?.uploadAdaptiveQuality !== false,
        convertHeic: this.flags?.heicConvertToJpeg !== false,
      });
      const prepared = await preparePhotoForUpload({
        uri: photo.uri,
        mimeType: photo.mime_type,
        displayName: photo.display_name,
        size: photo.size,
        width: photo.width,
        height: photo.height,
        limits: { maxFileSizeBytes: maxFileBytes },
        profile,
        adaptiveQualityEnabled: this.flags?.uploadAdaptiveQuality !== false,
      });
      const prepareMs = Math.max(0, Math.round(this.clock.nowMs() - prepareStartedAt));
      await this.repo.setPhotoUploadStatus(photo.id, 'queued', {
        progress: 0,
        localTransformUri: prepared.transformUri,
        originalSize: prepared.originalSize,
        uploadSize: prepared.size,
        errorCode: null,
        errorMessage: null,
        nextRetryAt: null,
      });
      // Phase 3 shadow scan: fire-and-forget after prepare; never fails upload.
      this.maybeRunLocalCodeScan({
        photo,
        sessionId,
        mode,
        preparedUri: prepared.transformUri || photo.uri,
        preparedBytes: prepared.size,
        preparedWidth: prepared.preparedWidth,
        preparedHeight: prepared.preparedHeight,
      });
      if (this.obs) {
        this.obs.marks.mark(photoMarkKey(sessionId, clientFileId, 'prepared'));
        emitObservability(this.obs.reporter, {
          name: 'photo.prepare_completed',
          sessionId,
          clientFileId,
          batchId: photo.upload_batch_id ?? undefined,
          durationMs: prepareMs,
          attributes: {
            prepare_ms: prepareMs,
            queued_to_prepare_started_ms: queuedWaitMs,
            preparation_profile_id: prepared.preparationProfileId,
            preparation_profile_version: prepared.preparationProfileVersion,
            preparation_processing_mode: mode,
            resize_applied: prepared.resizeApplied,
            reencode_applied: prepared.reencodeApplied,
            format_conversion_applied: prepared.formatConversionApplied,
            resize_reason: prepared.resizeReason,
            quality_applied: prepared.qualityApplied,
            ...prepareMetricAttributes({
              originalBytes: prepared.originalSize,
              preparedBytes: prepared.size,
              originalWidth: photo.width > 0 ? photo.width : null,
              originalHeight: photo.height > 0 ? photo.height : null,
              preparedWidth: prepared.preparedWidth > 0 ? prepared.preparedWidth : null,
              preparedHeight: prepared.preparedHeight > 0 ? prepared.preparedHeight : null,
              transformationProfile: prepared.transformationProfile,
              convertedFromHeic: prepared.convertedFromHeic,
            }),
            ...network,
          },
        });
      }
    } catch (e) {
      const prepareMs = Math.max(0, Math.round(this.clock.nowMs() - prepareStartedAt));
      const errorCode =
        e instanceof PrepareFileTooLargeError ? e.code : 'PREPARE_FAILED';
      await this.repo.setPhotoUploadStatus(photo.id, 'permanent_error', {
        errorCode,
        errorMessage: String(e),
      });
      emitObservability(this.obs?.reporter, {
        name: 'photo.prepare_failed',
        sessionId,
        clientFileId,
        batchId: photo.upload_batch_id ?? undefined,
        durationMs: prepareMs,
        attributes: {
          prepare_ms: prepareMs,
          error_code: normalizeObservabilityError({
            stage: 'prepare',
            code: errorCode,
            message: String(e),
          }),
        },
      });
    } finally {
      this.inFlightPhotos.delete(photo.id);
      this.emit();
      this.scheduleNativeDrain(sessionId);
    }
  }

  private maybeRunLocalCodeScan(input: {
    readonly photo: CapturePhotoRow;
    readonly sessionId: string;
    readonly mode: ReturnType<typeof normalizePreparationProcessingMode>;
    readonly preparedUri: string;
    readonly preparedBytes: number;
    readonly preparedWidth: number;
    readonly preparedHeight: number;
  }): void {
    const strategy = this.options.localCodeScan;
    if (!strategy) {
      return;
    }
    const flagEnabled = this.flags?.mobileLocalCodeScan === true;
    const fingerprint = hashPayloadFingerprint(
      `${input.preparedUri}|${input.preparedBytes}|${input.preparedWidth}x${input.preparedHeight}`,
    );
    void strategy
      .execute({
        capturePhotoId: input.photo.id,
        captureSessionId: input.sessionId,
        clientFileId: input.photo.client_file_id,
        preparedUri: input.preparedUri,
        preparedAssetFingerprint: fingerprint,
        processingMode: input.mode,
        flagEnabled,
        cancelRequested: input.photo.upload_cancel_requested === 1,
      })
      .catch((e) => {
        this.logger.warn('error', {
          code: 'LOCAL_CODE_SCAN_UNHANDLED',
          photoId: input.photo.id,
          message: String(e),
        });
      });
  }

  private async invalidatePreparedSize(photoId: string): Promise<void> {
    const photo = await this.repo.getPhotoById(photoId);
    if (!photo) {
      return;
    }
    await cleanupTransformUri(photo.local_transform_uri);
    await this.repo.setPhotoUploadStatus(photoId, 'queued', {
      localTransformUri: null,
      uploadSize: null,
      errorCode: null,
      errorMessage: null,
      nextRetryAt: null,
    });
  }

  /** HTTP upload for already-prepared photos (real sizes already packed). Slot must be acquired by caller. */
  private async uploadPreparedBatch(
    session: CaptureSessionRow,
    photoIds: readonly string[],
    packedBytes: number,
    concurrencyMeta: { readonly configuredConcurrency: number; readonly effectiveConcurrency: number },
  ): Promise<void> {
    let slotReleased = false;
    const releaseSlotOnce = (): void => {
      if (slotReleased) {
        return;
      }
      slotReleased = true;
      this.releaseUploadSlot();
    };

    try {
      const limits = await this.limits.ensureLoaded();
      const budget = this.packingBudget ?? (await this.syncPackingBudgetFromServer());
      for (const id of photoIds) {
        this.inFlightPhotos.add(id);
      }
      this.emit();

      const preparedFiles: { uri: string; name: string; mimeType: string }[] = [];
      const clientFileIds: string[] = [];
      const photoRows: CapturePhotoRow[] = [];
      const attemptId = createId();
      const abortController = new AbortController();
      this.uploadAbortByAttempt.set(attemptId, abortController);
      const network = networkAttributesFromConnectivity(this.connectivity);
      const batchId = session.upload_batch_id ?? undefined;
      let totalOriginalBytes = 0;
      let totalPreparedBytes = 0;

      try {
        for (const photoId of photoIds) {
          const photo = await this.repo.getPhotoById(photoId);
          if (!photo || !photo.client_file_id || !(photo.upload_size != null && photo.upload_size > 0)) {
            continue;
          }
          if (
            photo.upload_status === 'excluded' ||
            this.cancelledWhileUploading.has(photoId)
          ) {
            continue;
          }
          const uri = photo.local_transform_uri || photo.uri;
          const mimeType = photo.local_transform_uri
            ? 'image/jpeg'
            : photo.mime_type || 'image/jpeg';
          const name = photo.local_transform_uri
            ? photo.display_name.replace(/\.(heic|heif)$/i, '.jpg')
            : photo.display_name;
          const queuedToUploadMs =
            this.obs?.marks.takeElapsedMs(photoMarkKey(session.id, photo.client_file_id, 'prepared')) ??
            this.obs?.marks.takeElapsedMs(photoMarkKey(session.id, photo.client_file_id, 'queued')) ??
            null;
          const leaseToken = `js-${createId()}`;
          const leased = await this.repo.tryAcquireUploadLease({
            photoId,
            owner: UPLOAD_WORKER_OWNER_JS,
            token: leaseToken,
            expiresAt: leaseExpiresAtIso(),
          });
          if (!leased) {
            // Native (or another) owner holds the lease — do not race the upload.
            continue;
          }
          await this.repo.setPhotoUploadStatus(photoId, 'uploading', {
            progress: 0,
            incrementAttempts: true,
          });
          this.uploadAttemptByPhoto.set(photoId, attemptId);
          preparedFiles.push({
            uri,
            name,
            mimeType,
          });
          clientFileIds.push(photo.client_file_id);
          photoRows.push(photo);
          totalOriginalBytes += photo.original_size ?? photo.size ?? 0;
          totalPreparedBytes += photo.upload_size ?? 0;
          if (this.obs) {
            this.obs.marks.mark(photoMarkKey(session.id, photo.client_file_id, 'upload_started'));
            emitObservability(this.obs.reporter, {
              name: 'photo.upload_started',
              sessionId: session.id,
              clientFileId: photo.client_file_id,
              batchId,
              attemptId,
              attributes: {
                queued_to_upload_started_ms: queuedToUploadMs,
                prepared_bytes: photo.upload_size,
                upload_attempt_count: (photo.upload_attempts ?? 0) + 1,
                configured_concurrency: concurrencyMeta.configuredConcurrency,
                effective_concurrency: concurrencyMeta.effectiveConcurrency,
                active_upload_count: this.uploadSlots.activeCount,
                ...network,
              },
            });
          }
        }

        if (preparedFiles.length === 0) {
          return;
        }

        if (this.obs && batchId) {
          this.obs.marks.mark(batchMarkKey(batchId, 'upload_started'));
        }
        if (!this.firstUploadEmitted.has(session.id) && this.obs) {
          this.firstUploadEmitted.add(session.id);
          const sessionCreatedToFirstUpload =
            this.obs.marks.takeElapsedMs(sessionMarkKey(session.id, 'created')) ?? null;
          emitObservability(this.obs.reporter, {
            name: 'session.first_upload_started',
            sessionId: session.id,
            batchId,
            attemptId,
            durationMs: sessionCreatedToFirstUpload ?? undefined,
            attributes: {
              session_created_to_first_upload_ms: sessionCreatedToFirstUpload,
              ...network,
            },
          });
          this.obs.marks.mark(sessionMarkKey(session.id, 'first_upload'));
        }

        this.logger.info('upload_started', {
          sessionId: session.id,
          count: preparedFiles.length,
          packedBytes,
          maxFiles: budget.maxFiles,
          maxRequestBytes: budget.maxRequestBytes,
        });

        emitObservability(this.obs?.reporter, {
          name: 'batch.upload_started',
          sessionId: session.id,
          batchId,
          attemptId,
          attributes: {
            image_count: preparedFiles.length,
            total_original_bytes: totalOriginalBytes,
            total_prepared_bytes: totalPreparedBytes,
            packed_bytes: packedBytes,
            configured_concurrency: concurrencyMeta.configuredConcurrency,
            effective_concurrency: concurrencyMeta.effectiveConcurrency,
            active_upload_count: this.uploadSlots.activeCount,
            batch_attempt_count: 1,
            ...network,
          },
        });

        const uploadStartedAt = this.clock.nowMs();
        const response = await this.assetsApi.uploadBatch({
          inventoryId: session.inventory_id,
          aisleId: session.aisle_id,
          uploadBatchId: session.upload_batch_id!,
          clientFileIds,
          files: preparedFiles,
          ...(this.flags?.uploadAbortEnabled !== false ? { signal: abortController.signal } : {}),
        });
        const uploadMs = Math.max(0, Math.round(this.clock.nowMs() - uploadStartedAt));

        emitObservability(this.obs?.reporter, {
          name: 'batch.upload_completed',
          sessionId: session.id,
          batchId,
          attemptId,
          durationMs: uploadMs,
          attributes: {
            batch_upload_ms: uploadMs,
            image_count: preparedFiles.length,
            total_original_bytes: totalOriginalBytes,
            total_prepared_bytes: totalPreparedBytes,
            uploaded_count: response.uploaded?.length ?? 0,
            error_count: response.errors?.length ?? 0,
            configured_concurrency: concurrencyMeta.configuredConcurrency,
            effective_concurrency: concurrencyMeta.effectiveConcurrency,
            active_upload_count: this.uploadSlots.activeCount,
            ...network,
          },
        });

        const byClient = new Map(photoRows.map((p) => [p.client_file_id!, p]));
        for (const ok of response.uploaded ?? []) {
          const photo = ok.client_file_id ? byClient.get(ok.client_file_id) : undefined;
          if (!photo) {
            continue;
          }
          const current = await this.repo.getPhotoById(photo.id);
          const cancelled =
            this.cancelledWhileUploading.has(photo.id) ||
            current?.upload_status === 'excluded' ||
            current?.upload_status === 'remote_delete_pending' ||
            current?.upload_status === 'remote_deleted';
          if (cancelled) {
            this.cancelledWhileUploading.delete(photo.id);
            if (photo.local_transform_uri) {
              this.pendingTransformCleanup.add(photo.local_transform_uri);
            }
            await this.reconcileCancelledRemoteAsset(session, photo.id, ok.asset_id);
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
          emitObservability(this.obs?.reporter, {
            name: 'photo.upload_completed',
            sessionId: session.id,
            clientFileId: photo.client_file_id ?? undefined,
            batchId,
            attemptId,
            durationMs: uploadMs,
            attributes: {
              upload_ms: uploadMs,
              prepared_bytes: photo.upload_size,
              upload_attempt_count: photo.upload_attempts,
              upload_http_status: 200,
              upload_error_code: null,
              ...network,
            },
          });
        }

        for (const err of response.errors ?? []) {
          const photo = err.client_file_id ? byClient.get(err.client_file_id) : undefined;
          if (!photo) {
            continue;
          }
          if (
            this.cancelledWhileUploading.has(photo.id) ||
            (await this.repo.getPhotoById(photo.id))?.upload_status === 'excluded'
          ) {
            this.cancelledWhileUploading.delete(photo.id);
            if (photo.local_transform_uri) {
              this.pendingTransformCleanup.add(photo.local_transform_uri);
            }
            continue;
          }
          const retryable = isSoftPerFileRetryable(err.code);
          const attempt = photo.upload_attempts;
          const errorCode = normalizeObservabilityError({
            stage: 'upload',
            code: err.code,
            message: err.detail,
          });
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
            emitObservability(this.obs?.reporter, {
              name: 'photo.upload_retry',
              sessionId: session.id,
              clientFileId: photo.client_file_id ?? undefined,
              batchId,
              attemptId,
              attributes: {
                upload_attempt_count: attempt,
                upload_error_code: errorCode,
                retry_delay_ms: delay,
                ...network,
              },
            });
          } else {
            await this.repo.setPhotoUploadStatus(photo.id, 'permanent_error', {
              errorCode: err.code,
              errorMessage: err.detail,
            });
            emitObservability(this.obs?.reporter, {
              name: 'photo.upload_failed',
              sessionId: session.id,
              clientFileId: photo.client_file_id ?? undefined,
              batchId,
              attemptId,
              attributes: {
                upload_attempt_count: attempt,
                upload_error_code: errorCode,
                terminal: true,
                ...network,
              },
            });
          }
        }

        const accounted = new Set<string>();
        for (const ok of response.uploaded ?? []) {
          if (ok.client_file_id) accounted.add(ok.client_file_id);
        }
        for (const err of response.errors ?? []) {
          if (err.client_file_id) accounted.add(err.client_file_id);
        }
        for (const photo of photoRows) {
          const cid = photo.client_file_id;
          if (!cid || accounted.has(cid)) continue;
          if (
            this.cancelledWhileUploading.has(photo.id) ||
            (await this.repo.getPhotoById(photo.id))?.upload_status === 'excluded'
          ) {
            this.cancelledWhileUploading.delete(photo.id);
            if (photo.local_transform_uri) {
              this.pendingTransformCleanup.add(photo.local_transform_uri);
            }
            continue;
          }
          const delay = computeRetryDelayMs({
            attempt: photo.upload_attempts,
            baseDelayMs: limits.retry_base_delay_ms,
          });
          await this.repo.setPhotoUploadStatus(photo.id, 'retryable_error', {
            errorCode: 'UPLOAD_RESPONSE_INCOMPLETE',
            errorMessage: 'El backend no confirmó ni rechazó este archivo.',
            nextRetryAt: new Date(Date.now() + delay).toISOString(),
          });
        }

        if ((response.uploaded?.length ?? 0) > 0) {
          this.packingBudget = relaxPackingBudgetAfterSuccess({
            current: budget,
            server: {
              maxFilesPerRequest: limits.max_files_per_request,
              maxRequestSizeBytes: limits.max_request_size_bytes,
              maxFileSizeBytes: limits.max_file_size_bytes,
            },
          });
        }

        await this.refreshSessionReadiness(session.id);
        const readinessPhotos = await this.repo.listPhotos(session.id);
        const stillPending = readinessPhotos.some(
          (p) =>
            p.status === 'stable' &&
            ['not_queued', 'queued', 'preparing', 'uploading', 'retryable_error', 'remote_delete_pending'].includes(
              p.upload_status,
            ),
        );
        if (!stillPending && this.obs) {
          const allUploadsMs =
            this.obs.marks.takeElapsedMs(sessionMarkKey(session.id, 'created')) ?? null;
          emitObservability(this.obs.reporter, {
            name: 'session.all_uploads_completed',
            sessionId: session.id,
            batchId,
            durationMs: allUploadsMs ?? undefined,
            attributes: {
              session_created_to_all_uploads_completed_ms: allUploadsMs,
              ...network,
            },
          });
          this.obs.marks.mark(sessionMarkKey(session.id, 'all_uploads_completed'));
        }
      } catch (e) {
        const err = e instanceof ApiError ? e : null;
        const aborted = err?.code === REQUEST_ABORTED;
        if (aborted) {
          emitObservability(this.obs?.reporter, {
            name: 'batch.upload_aborted',
            sessionId: session.id,
            batchId,
            attemptId,
            attributes: {
              upload_error_code: REQUEST_ABORTED,
              image_count: photoIds.length,
              ...network,
            },
          });
          for (const photoId of photoIds) {
            if (this.cancelledWhileUploading.has(photoId)) {
              this.cancelledWhileUploading.delete(photoId);
              const photo = await this.repo.getPhotoById(photoId);
              if (photo?.local_transform_uri) {
                this.pendingTransformCleanup.add(photo.local_transform_uri);
              }
              continue;
            }
            const photo = await this.repo.getPhotoById(photoId);
            if (!photo || photo.upload_status === 'excluded' || photo.upload_status === 'uploaded') {
              continue;
            }
            // Sibling files: re-queue without network-style retry backoff.
            await this.repo.setPhotoUploadStatus(photoId, 'queued', {
              errorCode: REQUEST_ABORTED,
              errorMessage: 'La carga del lote fue cancelada.',
              nextRetryAt: null,
            });
          }
        } else {
          const klass =
            err?.code === REQUEST_TIMEOUT
              ? 'retryable'
              : classifyUploadHttpError(err?.status ?? null, err?.code ?? null);
          this.logger.warn('error', {
            where: 'upload_batch',
            sessionId: session.id,
            klass,
            status: err?.status ?? null,
            code: err?.code ?? null,
            message: err?.message ?? String(e),
            photoCount: photoIds.length,
            packedBytes,
          });
          const errorCode = normalizeObservabilityError({
            stage: 'upload',
            code: err?.code,
            httpStatus: err?.status,
            message: err?.message ?? String(e),
          });
          emitObservability(this.obs?.reporter, {
            name: 'batch.upload_failed',
            sessionId: session.id,
            batchId,
            attemptId,
            attributes: {
              upload_http_status: err?.status ?? null,
              upload_error_code: errorCode,
              image_count: photoIds.length,
              ...network,
            },
          });

          if (klass === 'auth') {
            for (const photoId of photoIds) {
              const photo = await this.repo.getPhotoById(photoId);
              if (!photo) continue;
              if (photo.upload_status === 'preparing' || photo.upload_status === 'uploading') {
                await this.repo.setPhotoUploadStatus(photoId, 'queued', {
                  errorCode: err?.code ?? 'AUTH_REQUIRED',
                  errorMessage: err?.message ?? String(e),
                  nextRetryAt: null,
                });
              }
            }
            await this.pause('auth');
          } else if (klass === 'payload_too_large') {
            await this.limits.refresh();
            const refreshed = await this.limits.ensureLoaded();
            this.packingBudget = shrinkPackingBudgetAfter413({
              current: budget,
              server: {
                maxFilesPerRequest: refreshed.max_files_per_request,
                maxRequestSizeBytes: refreshed.max_request_size_bytes,
                maxFileSizeBytes: refreshed.max_file_size_bytes,
              },
              failedBatchFileCount: photoIds.length,
              failedBatchBytes: packedBytes,
            });
            for (const photoId of photoIds) {
              const photo = await this.repo.getPhotoById(photoId);
              if (!photo) continue;
              if (photo.upload_status === 'excluded') {
                if (photo.local_transform_uri) {
                  this.pendingTransformCleanup.add(photo.local_transform_uri);
                }
                continue;
              }
              await cleanupTransformUri(photo.local_transform_uri);
              const delay = computeRetryDelayMs({
                attempt: photo.upload_attempts,
                baseDelayMs: Math.max(refreshed.retry_base_delay_ms, 2_000),
              });
              await this.repo.setPhotoUploadStatus(photoId, 'retryable_error', {
                errorCode: err?.code ?? 'UPLOAD_TOO_LARGE',
                errorMessage: err?.message ?? String(e),
                nextRetryAt: new Date(Date.now() + delay).toISOString(),
                localTransformUri: null,
                uploadSize: null,
              });
            }
            this.logger.warn('upload_retry', {
              sessionId: session.id,
              count: photoIds.length,
              code: err?.code ?? 'UPLOAD_TOO_LARGE',
              maxFiles: this.packingBudget.maxFiles,
              maxRequestBytes: this.packingBudget.maxRequestBytes,
              maxFileBytes: this.packingBudget.maxFileBytes,
            });
          } else if (klass === 'retryable') {
            for (const photoId of photoIds) {
              const photo = await this.repo.getPhotoById(photoId);
              if (!photo) continue;
              if (photo.upload_status === 'excluded') {
                if (photo.local_transform_uri) {
                  this.pendingTransformCleanup.add(photo.local_transform_uri);
                }
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
            this.logger.warn('upload_retry', {
              sessionId: session.id,
              count: photoIds.length,
              code: err?.code ?? 'NETWORK_ERROR',
            });
          } else if (klass === 'not_found' || klass === 'forbidden' || klass === 'validation') {
            for (const photoId of photoIds) {
              const photo = await this.repo.getPhotoById(photoId);
              if (photo?.upload_status === 'excluded') {
                if (photo.local_transform_uri) {
                  this.pendingTransformCleanup.add(photo.local_transform_uri);
                }
                continue;
              }
              await this.repo.setPhotoUploadStatus(photoId, 'permanent_error', {
                errorCode: err?.code ?? 'UPLOAD_FAILED',
                errorMessage: err?.message ?? String(e),
              });
            }
          } else {
            for (const photoId of photoIds) {
              const photo = await this.repo.getPhotoById(photoId);
              if (!photo) continue;
              if (photo.upload_status === 'excluded') {
                if (photo.local_transform_uri) {
                  this.pendingTransformCleanup.add(photo.local_transform_uri);
                }
                continue;
              }
              const delay = computeRetryDelayMs({
                attempt: photo.upload_attempts,
                baseDelayMs: limits.retry_base_delay_ms,
              });
              await this.repo.setPhotoUploadStatus(photoId, 'retryable_error', {
                errorCode: err?.code ?? 'UPLOAD_FAILED',
                errorMessage: err?.message ?? String(e),
                nextRetryAt: new Date(Date.now() + delay).toISOString(),
              });
            }
          }
        }
      } finally {
        this.uploadAbortByAttempt.delete(attemptId);
        for (const id of photoIds) {
          this.uploadAttemptByPhoto.delete(id);
          this.inFlightPhotos.delete(id);
        }
        await this.flushPendingTransformCleanup();
      }
    } finally {
      releaseSlotOnce();
      this.emit();
      this.scheduleTick(300);
    }
  }

  private async reclaimOrphanedInFlight(): Promise<void> {
    const now = Date.now();
    const sessions = await this.repo.listActivitySessions();
    for (const session of sessions) {
      const photos = await this.repo.listPhotosForUpload(session.id);
      for (const photo of photos) {
        if (photo.upload_status !== 'preparing' && photo.upload_status !== 'uploading') {
          continue;
        }
        const startedAt = photo.last_upload_attempt_at
          ? Date.parse(photo.last_upload_attempt_at)
          : 0;
        const stale = startedAt > 0 && now - startedAt > UPLOAD_STALE_MS;
        const orphan = !this.inFlightPhotos.has(photo.id);
        if (!orphan && !stale) {
          continue;
        }
        this.inFlightPhotos.delete(photo.id);
        const delay = computeRetryDelayMs({
          attempt: photo.upload_attempts,
          baseDelayMs: 2_000,
        });
        await this.repo.setPhotoUploadStatus(photo.id, 'retryable_error', {
          errorCode: stale ? 'UPLOAD_STALE' : 'UPLOAD_ORPHAN',
          errorMessage: stale
            ? 'La carga quedó colgada y se reintentará.'
            : 'La carga se interrumpió y se reintentará.',
          nextRetryAt: new Date(now + delay).toISOString(),
        });
        this.logger.info('recovery', {
          reason: stale ? 'stale_upload_reclaimed' : 'orphan_upload_reclaimed',
          photoId: photo.id,
          previous: photo.upload_status,
        });
      }
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

function needMoreWorkSoon(sessionCount: number): boolean {
  return sessionCount > 0;
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
