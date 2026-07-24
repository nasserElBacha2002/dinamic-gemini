import { compareCursor, cursorFromMarker, EMPTY_CURSOR, type CompositeCursor } from '../../core/compositeCursor';
import { createLogger, type Logger } from '../../core/logging';
import { detectNewPhotos } from '../../core/photoDetection';
import { createScanCoordinator, type ScanCoordinator } from '../../core/scanCoordinator';
import type { ScanMetrics } from '../../core/incrementalScan';
import { emptyScanMetrics } from '../../core/incrementalScan';
import type { CaptureMarker } from '../../domain/entities/captureMarker';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import type { CapturePhotoStatus } from '../../domain/enums/photoStatus';
import { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import { cursorFromInitialMarker, cursorFromSession, imageFromPhotoRow } from '../../database/schema/captureSchema';
import type { ForegroundService } from '../../native/foregroundService';
import type { IncrementalScanOptions, IncrementalScanResult, PermissionState } from '../../native/mediaStore';
import type { StabilityOutcome } from '../../native/stabilityProber';
import { emitObservability, sessionMarkKey } from '../../observability';

const VALIDATION_TIMEOUT_MS = 15_000;
/** Re-scan gallery while capture is active (missed MediaStore events / delayed indexing). */
const CATCHUP_SCAN_INTERVAL_MS = 4_000;

export interface StartCaptureInput {
  readonly inventoryId: string;
  readonly inventoryName: string;
  readonly aisleId: string;
  readonly aisleName: string;
  readonly permission: PermissionState;
}

export interface CaptureContext {
  readonly inventoryId: string;
  readonly inventoryName: string;
  readonly aisleId: string;
  readonly aisleName: string;
}

export interface CaptureSnapshot {
  readonly session: CaptureSessionRow | null;
  readonly context: CaptureContext | null;
  readonly photos: CapturePhotoRow[];
  readonly scanCursor: CompositeCursor;
  readonly lastValidCursor: CompositeCursor;
  readonly metrics: ScanMetrics;
  readonly scanInProgress: boolean;
  readonly pendingScan: boolean;
  readonly activeValidations: number;
  readonly fgsActive: boolean;
  readonly warning: string | null;
}

export interface CaptureMediaStore {
  queryMostRecentPhoto(): Promise<GalleryImage | null>;
  queryNewPhotosSince(options: IncrementalScanOptions): Promise<IncrementalScanResult>;
  subscribeToGalleryChanges(onChange: () => void): { remove: () => void };
  fileExists?(image: GalleryImage): Promise<boolean>;
}

export interface CaptureStabilityProber {
  probe(uri: string): Promise<StabilityOutcome>;
}

export interface CaptureServiceAdapters {
  readonly mediaStore?: CaptureMediaStore;
  readonly stabilityProber?: CaptureStabilityProber;
  readonly validationTimeoutMs?: number;
  readonly createId?: () => string;
  /** Called after a photo becomes stable (progressive upload hook). */
  readonly onPhotoStable?: (sessionId: string, photoId: string) => void | Promise<void>;
  /** Phase 0 observability (optional; never required for capture). */
  readonly observability?: {
    readonly reporter: import('../../observability').ObservabilityReporter;
    readonly marks: import('../../observability').TimingMarkStore;
  } | null;
}

type Listener = (snapshot: CaptureSnapshot) => void;

const defaultMediaStore: CaptureMediaStore = {
  async queryMostRecentPhoto() {
    throw new Error('Capture mediaStore adapter not configured.');
  },
  async queryNewPhotosSince() {
    throw new Error('Capture mediaStore adapter not configured.');
  },
  subscribeToGalleryChanges() {
    return { remove() {} };
  },
};

const defaultStabilityProber: CaptureStabilityProber = {
  async probe() {
    throw new Error('Capture stability prober adapter not configured.');
  },
};

export class OtherAisleCaptureActiveError extends Error {
  constructor(
    readonly otherSession: CaptureSessionRow,
  ) {
    super(
      `Hay otra captura activa en el pasillo ${otherSession.aisle_name}.`,
    );
    this.name = 'OtherAisleCaptureActiveError';
  }
}

export class CaptureService {
  private session: CaptureSessionRow | null = null;
  private photos: CapturePhotoRow[] = [];
  private scanCursor: CompositeCursor = EMPTY_CURSOR;
  /** Fixed session lower bound (start marker); anchors scanning so batches are never skipped. */
  private floorCursor: CompositeCursor = EMPTY_CURSOR;
  private lastValidCursor: CompositeCursor = EMPTY_CURSOR;
  private inspectedIds = new Set<string>();
  private coordinator: ScanCoordinator;
  private subscription: { remove: () => void } | null = null;
  private catchUpTimer: ReturnType<typeof setInterval> | null = null;
  private listeners = new Set<Listener>();
  private metrics: ScanMetrics = emptyScanMetrics();
  private fgsActive = false;
  private disposed = false;
  private autoScanEnabled = false;
  private warning: string | null = null;
  private activeValidations = new Map<string, Promise<void>>();
  private validationVersions = new Map<string, number>();
  private readonly mediaStore: CaptureMediaStore;
  private readonly stabilityProber: CaptureStabilityProber;
  private readonly validationTimeoutMs: number;
  private readonly createId: () => string;
  private readonly onPhotoStable: CaptureServiceAdapters['onPhotoStable'];
  private readonly observability: CaptureServiceAdapters['observability'];

  constructor(
    private readonly repo: CaptureRepository,
    private readonly foregroundService: ForegroundService,
    private readonly logger: Logger = createLogger(),
    adapters: CaptureServiceAdapters = {},
  ) {
    this.mediaStore = adapters.mediaStore ?? defaultMediaStore;
    this.stabilityProber = adapters.stabilityProber ?? defaultStabilityProber;
    this.validationTimeoutMs = adapters.validationTimeoutMs ?? VALIDATION_TIMEOUT_MS;
    this.createId = adapters.createId ?? createId;
    this.onPhotoStable = adapters.onPhotoStable;
    this.observability = adapters.observability ?? null;
    this.coordinator = createScanCoordinator(() => this.runScanOnce());
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot());
    return () => this.listeners.delete(listener);
  }

  async restoreLatestOpen(): Promise<CaptureSessionRow | null> {
    const sessions = await this.repo.listExclusiveCaptureSessions();
    if (sessions.length === 0) {
      this.clearCurrentSession();
      return null;
    }
    const [latest, ...stale] = sessions;
    if (!latest) {
      this.clearCurrentSession();
      return null;
    }
    if (stale.length > 0) {
      await this.repo.repairMultipleOpenSessions(latest.id, 'multiple_open_sessions_recovered');
      this.logger.warn('recovery', { reason: 'multiple_open_sessions_recovered', keptSessionId: latest.id, failedCount: stale.length });
      this.warning = 'Se detectaron múltiples sesiones locales; se conservó la más reciente.';
    }
    if (latest.status === 'active') {
      await this.repo.updateSessionStatus(latest.id, 'paused');
      this.warning = 'La captura fue interrumpida. Reanudala para continuar detectando fotografías.';
    }
    await this.loadSession(latest.id, false);
    this.logger.info('recovery', { sessionId: latest.id, status: latest.status });
    return this.session;
  }

  async listActivitySessions(): Promise<CaptureSessionRow[]> {
    return this.repo.listActivitySessions();
  }

  /**
   * Clears in-memory snapshot when navigating to a different aisle so UI does not
   * show photos/cursors from another capture.
   */
  prepareNewCapture(context: CaptureContext): void {
    const current = this.session;
    if (
      current &&
      (current.inventory_id !== context.inventoryId || current.aisle_id !== context.aisleId)
    ) {
      this.clearCurrentSession();
      this.warning = null;
      this.emit();
    }
  }

  async loadSession(sessionId: string, startListener: boolean): Promise<CaptureSnapshot> {
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      throw new Error('No se encontró la captura local.');
    }
    this.session = session;
    this.photos = await this.repo.listPhotos(session.id);
    this.scanCursor = cursorFromSession(session, 'scan');
    this.floorCursor = cursorFromInitialMarker(session);
    this.lastValidCursor = cursorFromSession(session, 'lastValid');
    this.inspectedIds = await this.repo.inspectedAssetIds(session.id);
    this.autoScanEnabled = startListener && session.status === 'active';
    if (this.autoScanEnabled) {
      await this.startForeground();
      this.attachListener();
    } else {
      this.detachListener();
    }
    this.emit();
    return this.getSnapshot();
  }

  /** Deterministic point-in-time read; prefer over subscribe-wrapped promises. */
  async getSessionSnapshot(sessionId: string): Promise<CaptureSnapshot> {
    const snapshot = await this.loadSession(sessionId, false);
    if (snapshot.session?.id !== sessionId) {
      throw new Error('No se pudo cargar la captura solicitada.');
    }
    return snapshot;
  }

  getSnapshot(): CaptureSnapshot {
    return this.snapshot();
  }

  async start(input: StartCaptureInput, options: { pauseOtherAisle?: boolean } = {}): Promise<void> {
    if (!input.permission.granted) {
      throw new Error('Se requieren permisos de fotografías.');
    }
    const exclusive = await this.repo.findExclusiveCaptureSession();
    if (exclusive && exclusive.aisle_id !== input.aisleId) {
      if (!options.pauseOtherAisle) {
        throw new OtherAisleCaptureActiveError(exclusive);
      }
      await this.loadSession(exclusive.id, false);
      if (exclusive.status === 'active' || exclusive.status === 'preparing' || exclusive.status === 'finishing') {
        await this.pause();
      } else {
        this.detachListener();
        await this.stopForeground();
      }
    } else if (exclusive && exclusive.aisle_id === input.aisleId) {
      await this.loadSession(exclusive.id, exclusive.status === 'active');
      this.warning = null;
      return;
    }

    const sameAislePaused = (await this.repo.listActivitySessions()).find(
      (s) =>
        s.aisle_id === input.aisleId &&
        s.inventory_id === input.inventoryId &&
        (s.status === 'paused' || s.status === 'review'),
    );
    if (sameAislePaused && !options.pauseOtherAisle) {
      // Prefer continuing existing local work for this aisle unless caller forces new.
      await this.loadSession(sameAislePaused.id, false);
      this.warning = null;
      return;
    }

    const recent = await this.mediaStore.queryMostRecentPhoto();
    const marker = buildMarker(input, recent);
    const result = await this.repo.createSessionExclusive({
      id: this.createId(),
      inventoryId: input.inventoryId,
      inventoryName: input.inventoryName,
      aisleId: input.aisleId,
      aisleName: input.aisleName,
      marker,
      uploadBatchId: this.createId(),
    });
    if (!result.created) {
      if (result.session.aisle_id !== input.aisleId) {
        throw new OtherAisleCaptureActiveError(result.session);
      }
      await this.loadSession(result.session.id, false);
      return;
    }
    this.session = result.session;
    this.photos = [];
    this.scanCursor = cursorFromMarker(marker);
    this.floorCursor = this.scanCursor;
    this.lastValidCursor = this.scanCursor;
    this.inspectedIds = new Set(recent?.assetId ? [recent.assetId] : []);
    try {
      await this.startForeground();
      await this.repo.updateSessionStatus(result.session.id, 'active');
      await this.loadSession(result.session.id, true);
      this.logger.info('session_start', {
        sessionId: result.session.id,
        inventoryId: input.inventoryId,
        aisleId: input.aisleId,
      });
      if (this.observability) {
        this.observability.marks.mark(sessionMarkKey(result.session.id, 'created'));
        emitObservability(this.observability.reporter, {
          name: 'session.created',
          sessionId: result.session.id,
          batchId: result.session.upload_batch_id ?? undefined,
        });
      }
    } catch (e) {
      this.detachListener();
      await this.stopForeground();
      await this.repo.updateSessionStatus(result.session.id, 'failed');
      await this.loadSession(result.session.id, false);
      throw e;
    }
  }

  async pause(): Promise<void> {
    const sessionId = this.requireSessionId();
    this.detachListener();
    this.autoScanEnabled = false;
    await this.repo.updateSessionStatus(sessionId, 'paused');
    await this.safeUpdateForeground('Pausada');
    await this.loadSession(sessionId, false);
  }

  async resume(permission?: PermissionState): Promise<void> {
    const sessionId = this.requireSessionId();
    if (permission && !permission.granted) {
      throw new Error('Se requieren permisos de fotografías.');
    }
    await this.recoverPendingValidations(sessionId);
    await this.startForeground();
    await this.repo.updateSessionStatus(sessionId, 'active');
    await this.loadSession(sessionId, true);
    await this.requestScan();
  }

  async finish(): Promise<void> {
    await this.finalizeCaptureForUpload({ targetStatus: 'review' });
  }

  /**
   * Single capture→upload handoff path. Stops autoscan, runs final scan/validation,
   * then transitions to review or uploading. Does not skip validation gates.
   */
  async finalizeCaptureForUpload(options?: {
    readonly targetStatus?: 'review' | 'uploading';
  }): Promise<string> {
    const target = options?.targetStatus ?? 'uploading';
    const sessionId = this.requireSessionId();
    const current = await this.repo.getSession(sessionId);
    if (!current) {
      throw new Error('No se encontró la captura local.');
    }

    if (current.status === 'uploading' && target === 'uploading') {
      this.clearCurrentSession();
      return sessionId;
    }

    // Uploads may finish during capture/local-review before completeReview runs.
    // Treat post-review pipeline states as an idempotent handoff to uploads UI.
    if (
      target === 'uploading' &&
      (current.status === 'upload_review' || current.status === 'ready_to_process')
    ) {
      this.clearCurrentSession();
      return sessionId;
    }

    if (current.status === 'review' && target === 'uploading') {
      await this.reloadPhotos(sessionId);
      this.assertPhotosReadyForUpload();
      await this.repo.updateSessionStatus(sessionId, 'uploading');
      this.clearCurrentSession();
      return sessionId;
    }

    if (current.status !== 'active' && current.status !== 'paused' && current.status !== 'finishing') {
      if (current.status === 'review' && target === 'review') {
        return sessionId;
      }
      throw new Error(
        `No se puede finalizar la captura desde el estado "${current.status}".`,
      );
    }

    if (current.status !== 'finishing') {
      await this.repo.updateSessionStatus(sessionId, 'finishing');
    }
    this.autoScanEnabled = false;
    this.detachListener();
    await this.loadSession(sessionId, false);
    await this.coordinator.request();
    await this.runScanOnce(sessionId, true);
    await this.waitForActiveValidations(sessionId, this.validationTimeoutMs);
    await this.markRemainingPendingAsInterrupted(sessionId, 'validation_timeout');
    await this.stopForeground();
    await this.reloadPhotos(sessionId);
    this.assertPhotosReadyForUpload();

    if (target === 'review') {
      await this.repo.updateSessionStatus(sessionId, 'review');
      await this.loadSession(sessionId, false);
      this.logger.info('session_finish', { sessionId });
      return sessionId;
    }

    await this.repo.updateSessionStatus(sessionId, 'review');
    await this.repo.updateSessionStatus(sessionId, 'uploading');
    this.clearCurrentSession();
    this.logger.info('session_finish', { sessionId, handoff: 'uploading' });
    return sessionId;
  }

  private assertPhotosReadyForUpload(): void {
    if (this.photos.some((p) => p.status === 'detected' || p.status === 'waiting_stability')) {
      throw new Error('Todavía hay fotografías validándose.');
    }
    if (this.photos.some((p) => p.status === 'unstable' || p.status === 'undecodable')) {
      throw new Error('Resolvé o excluí los errores antes de confirmar.');
    }
  }

  /**
   * Confirms local review and hands the session to the upload pipeline.
   * Does not mark the session completed until processing succeeds.
   */
  async completeReview(): Promise<string> {
    return this.finalizeCaptureForUpload({ targetStatus: 'uploading' });
  }

  async cancel(): Promise<void> {
    const sessionId = this.session?.id;
    if (!sessionId) return;
    this.detachListener();
    this.autoScanEnabled = false;
    await this.stopForeground();
    await this.repo.updateSessionStatus(sessionId, 'cancelled', true);
    this.clearCurrentSession();
  }

  async exclude(assetId: string): Promise<void> {
    const sessionId = this.requireSessionId();
    this.bumpValidationVersion(sessionId, assetId);
    await this.repo.updatePhotoStatus(sessionId, assetId, 'excluded');
    await this.reloadPhotos(sessionId);
  }

  async reincorporate(assetId: string): Promise<void> {
    const sessionId = this.requireSessionId();
    const row = this.photos.find((p) => p.asset_id === assetId);
    if (!row) return;
    await this.repo.updatePhotoStatus(sessionId, assetId, 'waiting_stability');
    await this.reloadPhotos(sessionId);
    this.scheduleValidation(sessionId, imageFromPhotoRow(row));
  }

  async retryErrors(): Promise<void> {
    const sessionId = this.requireSessionId();
    for (const row of this.photos) {
      if (['detected', 'waiting_stability', 'unstable', 'undecodable'].includes(row.status)) {
        const current = row.status;
        if (current !== 'waiting_stability') {
          await this.repo.updatePhotoStatus(sessionId, row.asset_id, 'waiting_stability');
        }
        this.scheduleValidation(sessionId, imageFromPhotoRow(row));
      }
    }
    await this.reloadPhotos(sessionId);
  }

  async recoverPendingValidations(sessionId: string): Promise<void> {
    const photos = await this.repo.listPhotos(sessionId);
    for (const row of photos) {
      if (row.status !== 'detected' && row.status !== 'waiting_stability') {
        continue;
      }
      const image = imageFromPhotoRow(row);
      const exists = this.mediaStore.fileExists ? await this.mediaStore.fileExists(image) : true;
      if (!exists) {
        await this.repo.applyStabilityResult({
          sessionId,
          assetId: row.asset_id,
          status: 'unstable',
          error: 'file_missing',
          checks: row.stability_checks,
        });
        continue;
      }
      if (row.status === 'detected') {
        await this.repo.updatePhotoStatus(sessionId, row.asset_id, 'waiting_stability');
      }
      this.scheduleValidation(sessionId, image);
    }
    await this.reloadPhotos(sessionId);
  }

  requestScan(): Promise<void> {
    if (!this.autoScanEnabled && this.session?.status !== 'active') {
      return Promise.resolve();
    }
    return this.coordinator.request();
  }

  dispose(): void {
    this.disposed = true;
    this.detachListener();
    this.listeners.clear();
  }

  private async runScanOnce(sessionId = this.session?.id, allowFinishing = false): Promise<void> {
    if (!sessionId) return;
    const session = await this.repo.getSession(sessionId);
    if (!session || (session.status !== 'active' && !(allowFinishing && session.status === 'finishing'))) {
      return;
    }
    const isCurrent = session.id === this.session?.id;
    const scanCursor = isCurrent ? this.scanCursor : cursorFromSession(session, 'scan');
    // Anchor scanning to the FIXED session start (floor), not the advancing scan cursor:
    // batch/same-second downloads and out-of-order indexing stay discoverable across scans.
    const floorCursor = isCurrent ? this.floorCursor : cursorFromInitialMarker(session);
    const inspectedIds = await this.repo.inspectedAssetIds(sessionId);
    const { images, metrics } = await this.mediaStore.queryNewPhotosSince({
      scanCursor,
      floorCursor,
      inspectedAssetIds: inspectedIds,
    });
    this.metrics = metrics;
    const result = detectNewPhotos({
      candidates: images,
      scanCursor: floorCursor,
      inspectedIds,
    });
    result.inspectedIds.forEach((id) => this.inspectedIds.add(id));
    // Keep the persisted scan cursor monotonic (telemetry only; paging uses the floor).
    const advancedScanCursor =
      compareCursor(result.nextScanCursor, scanCursor) > 0 ? result.nextScanCursor : scanCursor;
    await this.repo.updateScanCursor(sessionId, advancedScanCursor);
    if (isCurrent) {
      this.scanCursor = advancedScanCursor;
    }
    for (const rejected of result.rejected) {
      this.logger.info('photo_ignored', { assetId: rejected.assetId, reason: rejected.reason });
    }
    for (const image of result.admitted) {
      await this.repo.upsertPhoto(sessionId, image, 'detected');
      await this.repo.updatePhotoStatus(sessionId, image.assetId, 'waiting_stability');
      this.scheduleValidation(sessionId, image);
    }
    await this.reloadPhotos(sessionId);
  }

  private scheduleValidation(sessionId: string, image: GalleryImage): Promise<void> {
    const key = validationKey(sessionId, image.assetId);
    const existing = this.activeValidations.get(key);
    if (existing) {
      return existing;
    }
    const version = this.bumpValidationVersion(sessionId, image.assetId);
    const promise = this.validateImage(sessionId, image, version)
      .finally(() => {
        if (this.activeValidations.get(key) === promise) {
          this.activeValidations.delete(key);
          this.emit();
        }
      });
    this.activeValidations.set(key, promise);
    this.emit();
    return promise;
  }

  private async validateImage(sessionId: string, image: GalleryImage, version: number): Promise<void> {
    const session = await this.repo.getSession(sessionId);
    if (!session) return;
    const before = await this.repo.getPhoto(sessionId, image.assetId);
    if (!before || (before.status !== 'detected' && before.status !== 'waiting_stability')) return;
    const outcome = await this.stabilityProber.probe(image.uri);
    if (this.validationVersions.get(validationKey(sessionId, image.assetId)) !== version) return;
    const stillExists = await this.repo.getSession(sessionId);
    const photo = await this.repo.getPhoto(sessionId, image.assetId);
    if (!stillExists || !photo || (photo.status !== 'detected' && photo.status !== 'waiting_stability')) return;
    const failureReason = outcome.ok ? null : outcome.reason;
    const status: Extract<CapturePhotoStatus, 'stable' | 'unstable' | 'undecodable'> = outcome.ok
      ? 'stable'
      : failureReason === 'undecodable'
        ? 'undecodable'
        : 'unstable';
    const applied = await this.repo.applyStabilityResult({
      sessionId,
      assetId: image.assetId,
      status,
      error: failureReason,
      checks: outcome.checks,
    });
    if (!applied) return;
    if (status === 'stable') {
      const cursor = { dateAdded: image.dateAdded, assetId: image.assetId };
      if (compareCursor(cursor, this.lastValidCursor) > 0) {
        this.lastValidCursor = cursor;
        await this.repo.updateLastValidCursor(sessionId, cursor);
      }
      this.logger.info('photo_detected', { sessionId, assetId: image.assetId, status: 'stable' });
      const photoRow = await this.repo.getPhoto(sessionId, image.assetId);
      if (photoRow && this.onPhotoStable) {
        try {
          await this.onPhotoStable(sessionId, photoRow.id);
        } catch (e) {
          this.logger.warn('error', { where: 'on_photo_stable', message: String(e) });
        }
      }
    } else {
      this.logger.warn('file_unstable', { sessionId, assetId: image.assetId, reason: failureReason });
    }
    await this.reloadPhotos(sessionId);
    await this.safeUpdateForeground('Activa');
  }

  private async waitForActiveValidations(sessionId: string, timeoutMs: number): Promise<void> {
    const validations = Array.from(this.activeValidations.entries())
      .filter(([key]) => key.startsWith(`${sessionId}:`))
      .map(([, promise]) => promise);
    if (validations.length === 0) return;
    await Promise.race([
      Promise.allSettled(validations).then(() => undefined),
      sleep(timeoutMs),
    ]);
  }

  private async markRemainingPendingAsInterrupted(
    sessionId: string,
    error: 'validation_interrupted' | 'validation_timeout',
  ): Promise<void> {
    const photos = await this.repo.listPhotos(sessionId);
    for (const row of photos) {
      if (row.status === 'detected' || row.status === 'waiting_stability') {
        await this.repo.markValidationInterrupted(sessionId, row.asset_id, error);
      }
    }
  }

  private async reloadPhotos(sessionId: string): Promise<void> {
    if (this.session?.id !== sessionId) return;
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      this.clearCurrentSession();
      return;
    }
    this.session = session;
    this.photos = await this.repo.listPhotos(sessionId);
    this.scanCursor = cursorFromSession(session, 'scan');
    this.floorCursor = cursorFromInitialMarker(session);
    this.lastValidCursor = cursorFromSession(session, 'lastValid');
    this.emit();
  }

  private attachListener(): void {
    this.detachListener();
    this.subscription = this.mediaStore.subscribeToGalleryChanges(() => {
      if (this.autoScanEnabled) {
        void this.requestScan();
      }
    });
    // MediaStore events are often missed while the app is backgrounded (drone controller).
    // Periodic catch-up recovers photos once JS is running again.
    this.catchUpTimer = setInterval(() => {
      if (this.autoScanEnabled) {
        void this.requestScan();
      }
    }, CATCHUP_SCAN_INTERVAL_MS);
    // Avoid keeping Node test process alive if a test leaves capture active.
    this.catchUpTimer.unref?.();
  }

  private detachListener(): void {
    this.subscription?.remove();
    this.subscription = null;
    if (this.catchUpTimer) {
      clearInterval(this.catchUpTimer);
      this.catchUpTimer = null;
    }
  }

  private async startForeground(): Promise<void> {
    if (!this.foregroundService.isAvailable) {
      throw new Error('Foreground Service no disponible en este runtime.');
    }
    await this.foregroundService.start(this.notificationContent('Activa'));
    this.fgsActive = true;
  }

  private async safeUpdateForeground(_state: string): Promise<void> {
    if (!this.foregroundService.isAvailable || !this.fgsActive) return;
    try {
      await this.foregroundService.update(this.notificationContent('Activa'));
    } catch (e) {
      this.logger.warn('error', { where: 'fgs_update', message: String(e) });
    }
  }

  private async stopForeground(): Promise<void> {
    if (!this.foregroundService.isAvailable || !this.fgsActive) return;
    try {
      await this.foregroundService.stop();
    } catch (e) {
      this.logger.warn('error', { where: 'fgs_stop', message: String(e) });
    } finally {
      this.fgsActive = false;
    }
  }

  private notificationContent(_state: string) {
    const session = this.session;
    return {
      inventoryName: session?.inventory_name ?? 'Inventario',
      aisleName: session?.aisle_name ?? 'Pasillo',
      detected: this.photos.length,
      stable: this.photos.filter((p) => p.status === 'stable').length,
      pending: this.photos.filter((p) => p.status === 'waiting_stability' || p.status === 'detected').length,
    };
  }

  private requireSessionId(): string {
    if (!this.session) {
      throw new Error('No hay captura local activa.');
    }
    return this.session.id;
  }

  private bumpValidationVersion(sessionId: string, assetId: string): number {
    const key = validationKey(sessionId, assetId);
    const next = (this.validationVersions.get(key) ?? 0) + 1;
    this.validationVersions.set(key, next);
    return next;
  }

  private snapshot(): CaptureSnapshot {
    return {
      session: this.session,
      context: this.session ? contextFromSession(this.session) : null,
      photos: this.photos,
      scanCursor: this.scanCursor,
      lastValidCursor: this.lastValidCursor,
      metrics: this.metrics,
      scanInProgress: this.coordinator.isInProgress,
      pendingScan: this.coordinator.hasPending,
      activeValidations: this.activeValidations.size,
      fgsActive: this.fgsActive,
      warning: this.warning,
    };
  }

  private emit(): void {
    if (this.disposed) return;
    const snap = this.snapshot();
    this.listeners.forEach((listener) => listener(snap));
  }

  private clearCurrentSession(): void {
    this.session = null;
    this.photos = [];
    this.scanCursor = EMPTY_CURSOR;
    this.floorCursor = EMPTY_CURSOR;
    this.lastValidCursor = EMPTY_CURSOR;
    this.inspectedIds = new Set();
    this.metrics = emptyScanMetrics();
    this.autoScanEnabled = false;
    this.fgsActive = false;
    this.warning = null;
    this.detachListener();
    this.emit();
  }
}

function contextFromSession(session: CaptureSessionRow): CaptureContext {
  return {
    inventoryId: session.inventory_id,
    inventoryName: session.inventory_name,
    aisleId: session.aisle_id,
    aisleName: session.aisle_name,
  };
}

function buildMarker(input: StartCaptureInput, recent: GalleryImage | null): CaptureMarker {
  return {
    assetId: recent?.assetId ?? null,
    mediaStoreNumericId: recent?.mediaStoreNumericId ?? null,
    dateAdded: recent?.dateAdded ?? null,
    dateModified: recent?.dateModified ?? null,
    displayName: recent?.displayName ?? null,
    size: recent?.size ?? null,
    bucketId: recent?.bucketId ?? null,
    inventoryId: input.inventoryId,
    aisleId: input.aisleId,
  };
}

function validationKey(sessionId: string, assetId: string): string {
  return `${sessionId}:${assetId}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function createId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

