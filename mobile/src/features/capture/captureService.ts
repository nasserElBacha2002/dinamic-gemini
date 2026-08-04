import { compareCursor, cursorFromMarker, EMPTY_CURSOR, type CompositeCursor } from '../../core/compositeCursor';
import { createLogger, type Logger } from '../../core/logging';
import { detectNewPhotos } from '../../core/photoDetection';
import { createScanCoordinator, type ScanCoordinator } from '../../core/scanCoordinator';
import type { ScanMetrics } from '../../core/incrementalScan';
import { emptyScanMetrics } from '../../core/incrementalScan';
import type { CaptureMarker } from '../../domain/entities/captureMarker';
import type { GalleryImage } from '../../domain/entities/galleryImage';
import type { CapturePhotoStatus, CaptureSessionStatus } from '../../domain/enums/photoStatus';
import { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import { cursorFromInitialMarker, cursorFromSession, imageFromPhotoRow } from '../../database/schema/captureSchema';
import type { ForegroundService } from '../../native/foregroundService';
import type { IncrementalScanOptions, IncrementalScanResult, PermissionState } from '../../native/mediaStore';
import type { StabilityOutcome } from '../../native/stabilityProber';
import { emitObservability, sessionMarkKey } from '../../observability';
import {
  countFinishPhotos,
  emitFinishEvent,
  finishBaseAttributes,
  stageDurationMs,
  type CaptureFinishStage,
} from './finishObservability';
import { CaptureFreezeService } from './captureFreezeService';

export type UploadPolicy = 'MANUAL' | 'WHEN_CONNECTED' | 'NOW';

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
  /** User-visible finish progress stage (null when not finishing). */
  readonly finishStage: CaptureFinishStage;
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
  /** Emit capture.finish_* events (default true when observability is set). */
  readonly finishInstrumentation?: boolean;
  /** Light MediaStore check before skipping full rescan (default true). */
  readonly finishSafeMediaCheck?: boolean;
  /** Persist freeze watermark on successful finish (default true). */
  readonly sessionFreeze?: boolean;
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
  private finishStage: CaptureFinishStage = null;
  private finishInFlight: Promise<string> | null = null;
  private activeValidations = new Map<string, Promise<void>>();
  private validationVersions = new Map<string, number>();
  private readonly mediaStore: CaptureMediaStore;
  private readonly stabilityProber: CaptureStabilityProber;
  private readonly validationTimeoutMs: number;
  private readonly createId: () => string;
  private readonly onPhotoStable: CaptureServiceAdapters['onPhotoStable'];
  private readonly observability: CaptureServiceAdapters['observability'];
  private readonly finishInstrumentation: boolean;
  private readonly finishSafeMediaCheck: boolean;
  private readonly sessionFreeze: boolean;
  private readonly freezeService: CaptureFreezeService;
  private sqliteBusyCountFinish = 0;

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
    this.finishInstrumentation = adapters.finishInstrumentation ?? true;
    this.finishSafeMediaCheck = adapters.finishSafeMediaCheck ?? true;
    this.sessionFreeze = adapters.sessionFreeze ?? true;
    this.freezeService = new CaptureFreezeService(repo);
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
    if (this.finishInFlight) {
      return this.finishInFlight;
    }
    const tracked: { current: Promise<string> | null } = { current: null };
    tracked.current = this.runFinalizeCaptureForUpload(options).finally(() => {
      if (this.finishInFlight === tracked.current) {
        this.finishInFlight = null;
      }
    });
    this.finishInFlight = tracked.current;
    return tracked.current;
  }

  private async runFinalizeCaptureForUpload(options?: {
    readonly targetStatus?: 'review' | 'uploading';
  }): Promise<string> {
    const target = options?.targetStatus ?? 'uploading';
    const sessionId = this.requireSessionId();
    const finishStartedAt = Date.now();
    let errorStage = 'start';
    const current = await this.repo.getSession(sessionId);
    if (!current) {
      throw new Error('No se encontró la captura local.');
    }
    const statusBefore = current.status;

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

    // Remember pre-finish status so gate failures can restore a usable capture state.
    // Sessions already stuck in `finishing` (legacy) resume as active.
    const resumeStatus: 'active' | 'paused' =
      current.status === 'paused' ? 'paused' : 'active';

    this.emitFinishObs('capture.finish_started', sessionId, current, {
      statusBefore,
      statusAfter: 'finishing',
      durationMs: 0,
    });

    await this.ensureSessionStatus(sessionId, 'finishing', ['active', 'paused', 'finishing']);
    this.autoScanEnabled = false;
    this.detachListener();
    // Emit finishing immediately so CaptureScreen can show loading before heavy work.
    if (this.session?.id === sessionId) {
      this.session = { ...this.session, status: 'finishing' };
      this.setFinishStage('checking_media');
    }

    try {
      errorStage = 'session_loaded';
      const loadStarted = Date.now();
      await this.loadSession(sessionId, false);
      const sessionAfterLoad = this.session ?? (await this.repo.getSession(sessionId));
      if (!sessionAfterLoad) {
        throw new Error('No se encontró la captura local.');
      }
      this.emitFinishObs('capture.finish_session_loaded', sessionId, sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: stageDurationMs(loadStarted),
      });

      const hasPendingValidation = this.photos.some(
        (p) => p.status === 'detected' || p.status === 'waiting_stability',
      );
      const sessionValidationCount = Array.from(this.activeValidations.keys()).filter((key) =>
        key.startsWith(`${sessionId}:`),
      ).length;
      this.emitFinishObs('capture.finish_pending_validation_count', sessionId, sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: 0,
        activeValidationCount: sessionValidationCount,
      });

      // Light MediaStore check: SQLite-stable alone can miss gallery photos not yet admitted.
      let newMediaCandidateCount = 0;
      if (this.finishSafeMediaCheck) {
        errorStage = 'media_store_check';
        this.setFinishStage('checking_media');
        const mediaCheckStarted = Date.now();
        this.emitFinishObs('capture.finish_media_store_check_started', sessionId, sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: 0,
        });
        newMediaCandidateCount = await this.countNewMediaCandidates(sessionId);
        this.emitFinishObs('capture.finish_media_store_check_completed', sessionId, sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: stageDurationMs(mediaCheckStarted),
          newMediaCandidateCount,
        });
        this.emitFinishObs('capture.finish_new_media_candidates', sessionId, sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: 0,
          newMediaCandidateCount,
        });
      }

      const needsScanOrValidation =
        hasPendingValidation || sessionValidationCount > 0 || newMediaCandidateCount > 0;

      if (needsScanOrValidation) {
        errorStage = 'scan';
        this.setFinishStage(newMediaCandidateCount > 0 ? 'checking_media' : 'validating');
        const scanStarted = Date.now();
        this.emitFinishObs('capture.finish_scan_started', sessionId, sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: 0,
          newMediaCandidateCount,
          skippedFullRescan: false,
        });
        await this.coordinator.request();
        await this.runScanOnce(sessionId, true);
        this.emitFinishObs('capture.finish_scan_completed', sessionId, this.session ?? sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: stageDurationMs(scanStarted),
          newMediaCandidateCount,
          skippedFullRescan: false,
        });

        errorStage = 'validation_wait';
        this.setFinishStage('validating');
        const waitStarted = Date.now();
        this.emitFinishObs('capture.finish_validation_wait_started', sessionId, this.session ?? sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: 0,
          activeValidationCount: this.activeValidations.size,
        });
        await this.waitForActiveValidations(sessionId, this.validationTimeoutMs);
        await this.markRemainingPendingAsInterrupted(sessionId, 'validation_timeout');
        this.emitFinishObs('capture.finish_validation_wait_completed', sessionId, this.session ?? sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: stageDurationMs(waitStarted),
          activeValidationCount: this.activeValidations.size,
        });

        // Second light check: photos indexed during validation window.
        if (this.finishSafeMediaCheck) {
          const lateCandidates = await this.countNewMediaCandidates(sessionId);
          if (lateCandidates > 0) {
            await this.runScanOnce(sessionId, true);
            await this.waitForActiveValidations(sessionId, this.validationTimeoutMs);
            await this.markRemainingPendingAsInterrupted(sessionId, 'validation_timeout');
            newMediaCandidateCount += lateCandidates;
          }
        }
      } else {
        this.emitFinishObs('capture.finish_scan_completed', sessionId, sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: 0,
          newMediaCandidateCount: 0,
          skippedFullRescan: true,
        });
      }

      errorStage = 'foreground_stop';
      this.setFinishStage('closing');
      const fgsStarted = Date.now();
      this.emitFinishObs('capture.finish_foreground_stop_started', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: 0,
        foregroundServiceActive: this.fgsActive,
      });
      await this.stopForeground();
      this.emitFinishObs('capture.finish_foreground_stop_completed', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: stageDurationMs(fgsStarted),
        foregroundServiceActive: false,
      });

      errorStage = 'reload_photos';
      const reloadStarted = Date.now();
      this.emitFinishObs('capture.finish_reload_photos_started', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: 0,
      });
      await this.reloadPhotos(sessionId);
      this.emitFinishObs('capture.finish_reload_photos_completed', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: stageDurationMs(reloadStarted),
      });

      errorStage = 'readiness_check';
      const readyStarted = Date.now();
      this.emitFinishObs('capture.finish_readiness_check_started', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: 0,
      });
      this.assertPhotosReadyForUpload();
      this.emitFinishObs('capture.finish_readiness_check_completed', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: stageDurationMs(readyStarted),
      });

      if (this.sessionFreeze) {
        const frozen = await this.freezeService.freezeSession(sessionId, this.photos);
        this.sqliteBusyCountFinish = 0;
        if (this.session?.id === sessionId) {
          const refreshed = await this.repo.getSession(sessionId);
          if (refreshed) {
            this.session = refreshed;
          }
        }
        this.emitFinishObs('capture.finish_freeze_completed', sessionId, this.session ?? sessionAfterLoad, {
          statusBefore,
          statusAfter: 'finishing',
          durationMs: 0,
          newMediaCandidateCount: frozen.photoCount,
        });
        this.logger.info('session_finish', {
          sessionId,
          handoff: 'freeze_snapshot',
          freezeId: frozen.freezeId,
          photoCount: frozen.photoCount,
        });
      }

      // Re-assert finishing before review: concurrent writers / SQLite recovery can
      // leave the row on `active`, which cannot jump directly to `review`.
      await this.ensureSessionStatus(sessionId, 'finishing', ['active', 'paused', 'finishing']);

      errorStage = 'review_transition';
      this.setFinishStage('preparing_review');
      const reviewStarted = Date.now();
      this.emitFinishObs('capture.finish_review_transition_started', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'finishing',
        durationMs: 0,
        newMediaCandidateCount,
        skippedFullRescan: !needsScanOrValidation,
      });
      await this.repo.updateSessionStatus(sessionId, 'review');
      this.emitFinishObs('capture.finish_review_transition_completed', sessionId, this.session ?? sessionAfterLoad, {
        statusBefore,
        statusAfter: 'review',
        durationMs: stageDurationMs(reviewStarted),
        newMediaCandidateCount,
        skippedFullRescan: !needsScanOrValidation,
      });

      if (target === 'review') {
        await this.loadSession(sessionId, false);
        this.setFinishStage(null);
        this.emitFinishObs('capture.finish_completed', sessionId, this.session ?? sessionAfterLoad, {
          statusBefore,
          statusAfter: 'review',
          durationMs: stageDurationMs(finishStartedAt),
          newMediaCandidateCount,
          skippedFullRescan: !needsScanOrValidation,
        });
        this.logger.info('session_finish', { sessionId });
        return sessionId;
      }

      await this.repo.updateSessionStatus(sessionId, 'uploading');
      this.setFinishStage(null);
      this.emitFinishObs('capture.finish_completed', sessionId, sessionAfterLoad, {
        statusBefore,
        statusAfter: 'uploading',
        durationMs: stageDurationMs(finishStartedAt),
        newMediaCandidateCount,
        skippedFullRescan: !needsScanOrValidation,
      });
      this.clearCurrentSession();
      this.logger.info('session_finish', { sessionId, handoff: 'uploading' });
      return sessionId;
    } catch (error) {
      // Keep capture operable after unresolved unstable/undecodable (or other gate) failures.
      const stillFinishing = (await this.repo.getSession(sessionId))?.status === 'finishing';
      if (stillFinishing) {
        await this.repo.updateSessionStatus(sessionId, resumeStatus);
        await this.loadSession(sessionId, resumeStatus === 'active');
      }
      this.setFinishStage(null);
      const failedSession = (await this.repo.getSession(sessionId)) ?? current;
      this.emitFinishObs('capture.finish_failed', sessionId, failedSession, {
        statusBefore,
        statusAfter: failedSession.status,
        durationMs: stageDurationMs(finishStartedAt),
        errorCode: 'FINISH_FAILED',
        errorStage,
      });
      throw error;
    }
  }

  private setFinishStage(stage: CaptureFinishStage): void {
    this.finishStage = stage;
    this.emit();
  }

  private emitFinishObs(
    name: string,
    sessionId: string,
    session: CaptureSessionRow,
    extra: {
      readonly statusBefore?: string | null;
      readonly statusAfter?: string | null;
      readonly durationMs?: number;
      readonly activeValidationCount?: number;
      readonly newMediaCandidateCount?: number | null;
      readonly errorCode?: string | null;
      readonly errorStage?: string | null;
      readonly foregroundServiceActive?: boolean | null;
      readonly skippedFullRescan?: boolean | null;
    },
  ): void {
    if (!this.finishInstrumentation || !this.observability?.reporter) {
      return;
    }
    const attributes = finishBaseAttributes({
      session,
      photos: this.photos,
      statusBefore: extra.statusBefore ?? null,
      statusAfter: extra.statusAfter ?? null,
      activeValidationCount: extra.activeValidationCount ?? this.activeValidations.size,
      newMediaCandidateCount: extra.newMediaCandidateCount ?? null,
      sqliteBusyCount: this.sqliteBusyCountFinish,
      errorCode: extra.errorCode ?? null,
      errorStage: extra.errorStage ?? null,
      foregroundServiceActive: extra.foregroundServiceActive ?? this.fgsActive,
      finishStage: this.finishStage,
      skippedFullRescan: extra.skippedFullRescan ?? null,
    });
    if (extra.durationMs != null) {
      emitFinishEvent(this.observability.reporter, {
        name,
        sessionId,
        durationMs: extra.durationMs,
        attributes,
      });
      return;
    }
    emitFinishEvent(this.observability.reporter, {
      name,
      sessionId,
      attributes,
    });
  }

  /**
   * Count gallery candidates newer than the session floor that are not yet admitted.
   * Does not mutate SQLite; used to decide whether a finishing rescan is required.
   */
  private async countNewMediaCandidates(sessionId: string): Promise<number> {
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      return 0;
    }
    const isCurrent = session.id === this.session?.id;
    const scanCursor = isCurrent ? this.scanCursor : cursorFromSession(session, 'scan');
    const floorCursor = isCurrent ? this.floorCursor : cursorFromInitialMarker(session);
    const inspectedIds = await this.repo.inspectedAssetIds(sessionId);
    const { images } = await this.mediaStore.queryNewPhotosSince({
      scanCursor,
      floorCursor,
      inspectedAssetIds: inspectedIds,
    });
    const result = detectNewPhotos({
      candidates: images,
      scanCursor: floorCursor,
      inspectedIds,
    });
    return result.admitted.length;
  }

  /**
   * Idempotent session transition helper. Re-reads status and applies `to` when needed.
   * Prevents illegal jumps (e.g. active → review) when a prior write did not stick.
   */
  private async ensureSessionStatus(
    sessionId: string,
    to: CaptureSessionStatus,
    allowedFrom: readonly CaptureSessionStatus[],
  ): Promise<void> {
    const row = await this.repo.getSession(sessionId);
    if (!row) {
      throw new Error('No se encontró la captura local.');
    }
    if (row.status === to) {
      return;
    }
    if (!allowedFrom.includes(row.status)) {
      throw new Error(
        `No se puede finalizar la captura desde el estado "${row.status}".`,
      );
    }
    await this.repo.updateSessionStatus(sessionId, to);
    const after = await this.repo.getSession(sessionId);
    if (!after || after.status !== to) {
      throw new Error(
        'No se pudo actualizar el estado de la captura. Probá de nuevo; si persiste, reiniciá la app.',
      );
    }
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

  /**
   * Close the aisle locally without requiring upload or /process.
   * Upload scheduling follows uploadPolicy; MANUAL never enqueues.
   */
  async completeLocalSession(options?: {
    readonly uploadPolicy?: UploadPolicy;
  }): Promise<{ readonly sessionId: string; readonly uploadPolicy: UploadPolicy }> {
    const sessionId = this.requireSessionId();
    const policy: UploadPolicy = options?.uploadPolicy ?? 'MANUAL';
    const current = await this.repo.getSession(sessionId);
    if (!current) {
      throw new Error('No se encontró la captura local.');
    }
    if (current.status === 'local_completed') {
      return { sessionId, uploadPolicy: (current.upload_policy as UploadPolicy) ?? policy };
    }
    if (current.status === 'review') {
      await this.reloadPhotos(sessionId);
      this.assertPhotosReadyForUpload();
      if (this.sessionFreeze && !current.active_freeze_id) {
        await this.freezeService.freezeSession(sessionId, this.photos);
      }
      await this.repo.setUploadPolicy(sessionId, policy);
      await this.repo.updateSessionStatus(sessionId, 'local_completed');
      await this.loadSession(sessionId, false);
      this.logger.info('session_finish', {
        sessionId,
        handoff: 'local_completed',
        uploadPolicy: policy,
      });
      return { sessionId, uploadPolicy: policy };
    }
    if (current.status === 'active' || current.status === 'paused' || current.status === 'finishing') {
      await this.finalizeCaptureForUpload({ targetStatus: 'review' });
      return this.completeLocalSession(options);
    }
    throw new Error(
      `No se puede cerrar localmente desde el estado "${current.status}".`,
    );
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
    const photo = await this.repo.getPhoto(sessionId, assetId);
    if (photo) {
      await this.repo.clearPhotoSequenceNumber(photo.id);
    }
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
    // Assign sequence_number at first persist (gallery order), before stability/prep.
    // Multi-admit and single (direct) capture share this transactional path.
    await this.repo.upsertAdmittedPhotosWithSequences(sessionId, result.admitted, 'detected');
    for (const image of result.admitted) {
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
    const applied = await this.repo.applyStabilityResult(
      {
        sessionId,
        assetId: image.assetId,
        status,
        error: failureReason,
        checks: outcome.checks,
      },
      {
        onBusyRetry: ({ attempt, maxAttempts }) => {
          this.sqliteBusyCountFinish += 1;
          emitObservability(this.observability?.reporter ?? null, {
            name: 'sqlite.busy_retry',
            sessionId,
            attributes: {
              attempt,
              max_attempts: maxAttempts,
              scope: 'stability',
            },
          });
        },
      },
    );
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
      finishStage: this.finishStage,
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
    this.finishStage = null;
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

