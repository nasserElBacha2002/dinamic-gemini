import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import {
  ExportPrepFenceError,
  ExportPrepRepository,
} from '../../database/repositories/exportPrepRepository';
import type { LocalDetectionDraftRepository } from '../../database/repositories/localDetectionDraftRepository';
import type { Logger } from '../../core/logging';
import { hashPreparedFileSha256, hashPreparedMetaSha256 } from '../localCodeScan/preparedAssetHash';
import type { LocalCodeScanStrategy } from '../localCodeScan/localCodeScanStrategy';
import {
  normalizePreparationProcessingMode,
  resolveLocalScanProcessingMode,
} from '../../core/imagePreparationPolicy';
import { isDraftExportReady } from '../localCsv/supplierExportSemantics';
import { exportPhotoFileName } from './exportPhotoFileName';
import {
  stageOriginalPhotoVersioned,
  deleteSessionExportStaging,
} from './exportStaging';
import type { ExportPrepCounts, ExportPrepJobRow, EnsureExportPrepJobsResult, ExportPrepEnsureReason } from './exportPrepTypes';
import { emptyExportPrepCounts, emptyEnsureExportPrepJobsResult } from './exportPrepTypes';
import {
  buildJobsSnapshotToken,
  canAttachJobsSnapshot,
} from './jobsSnapshotFence';
import { hashStagedFileSha256Detailed, classifyStagedDigestError } from './stagedSha256';
import { assertNativeDigestCapability } from './digestAbsoluteFile';
import {
  listCanonicalExportPhotos,
  selectEligibleExportPrepPhotos,
  selectNonProcessableExportPhotos,
} from './eligibleExportPhotos';
import {
  sourceUriIsReadable,
  validateReadyStaging,
  type ReadyValidationMode,
} from './validateReadyStaging';

export type { ExportPrepCounts, EnsureExportPrepJobsResult, ExportPrepEnsureReason } from './exportPrepTypes';
export { emptyExportPrepCounts, emptyEnsureExportPrepJobsResult };

/** Optional debug/benchmark stage observer — no-op when unset (production path unchanged). */
export type ExportPrepStageObserver = {
  onStage(event: {
    readonly stage:
      | 'staging_copy'
      | 'local_scan'
      | 'staging_hash'
      | 'draft_lookup'
      | 'draft_lookup_pre_scan'
      | 'draft_lookup_post_scan';
    readonly photoId: string;
    readonly sequence: number | null;
    readonly monotonicStartMs: number;
    readonly durationMs: number;
    readonly inputBytes: number | null;
    readonly outputBytes: number | null;
    readonly queueDepth: number | null;
    readonly workerConcurrency: number | null;
    readonly executionContext: 'js' | 'native' | 'unknown';
    readonly success: boolean;
    readonly errorCode: string | null;
    readonly extras?: Readonly<Record<string, number | string | boolean | null>>;
  }): void;
};

export type DraftLookupPurpose = 'skip_scan_check' | 'export_ready_check';

export interface ExportPrepQueueDeps {
  readonly prepRepo: ExportPrepRepository;
  readonly captureRepo: CaptureRepository;
  readonly draftRepo: LocalDetectionDraftRepository;
  readonly localCodeScan: LocalCodeScanStrategy | null;
  readonly localCodeScanEnabled: boolean;
  readonly logger?: Logger | null;
  readonly maxWorkers?: number;
  /** Soft warning threshold — never drops photos. */
  readonly warningPendingThreshold?: number;
  /** Soft max estimated ZIP payload bytes (reject controlled). Default 480 MiB. */
  readonly maxExportUncompressedBytes?: number;
}

export type ExportPrepListener = (sessionId: string | null, counts: ExportPrepCounts) => void;

export interface ExportPrepSettleResult {
  readonly ok: boolean;
  readonly totalEligible: number;
  readonly ready: number;
  readonly excluded: number;
  readonly failed: number;
  readonly pending: number;
  readonly missingJobs: number;
  readonly failedTerminal: number;
  readonly failedRetryable: number;
}

/** Phase 3 drain observation result (authoritative snapshot). */
export type ExportPrepStructuralError =
  | 'SESSION_MISSING'
  | 'FREEZE_MISSING'
  | 'FREEZE_CHANGED'
  | 'DRAIN_FAILED'
  | 'DATABASE_ERROR'
  | 'STORAGE_ERROR'
  | null;

export interface ExportPrepDrainResult {
  readonly sessionId: string;
  readonly sessionExists: boolean;
  readonly canonicalSnapshotAvailable: boolean;
  readonly freezeId: string | null;
  readonly freezeGeneration: number | null;
  readonly totalEligible: number;
  readonly ready: number;
  readonly queued: number;
  readonly processing: number;
  readonly failedRetryable: number;
  readonly failedTerminal: number;
  readonly missingJobs: number;
  readonly excluded: number;
  readonly timedOut: boolean;
  /** Must be an explicit boolean from the coordinator — never defaulted to true. */
  readonly producerBarrierCompleted: boolean;
  readonly structuralError: ExportPrepStructuralError;
  readonly exportable: boolean;
  readonly durationMs: number;
  readonly backfillPartialErrors: readonly string[];
  readonly missingSourcePhotos: number;
}

export function emptyExportPrepDrainResult(
  sessionId: string,
  partial?: Partial<ExportPrepDrainResult>,
): ExportPrepDrainResult {
  return {
    sessionId,
    sessionExists: false,
    canonicalSnapshotAvailable: false,
    freezeId: null,
    freezeGeneration: null,
    totalEligible: 0,
    ready: 0,
    queued: 0,
    processing: 0,
    failedRetryable: 0,
    failedTerminal: 0,
    missingJobs: 0,
    excluded: 0,
    timedOut: false,
    producerBarrierCompleted: false,
    structuralError: 'SESSION_MISSING',
    exportable: false,
    durationMs: 0,
    backfillPartialErrors: [],
    missingSourcePhotos: 0,
    ...partial,
  };
}

export interface WaitUntilExportableOptions {
  readonly timeoutMs?: number;
  readonly pollMs?: number;
  /** Explicit proof from coordinator; required — no silent default to true. */
  readonly producerBarrierCompleted: boolean;
  readonly reason?: ExportPrepEnsureReason;
  readonly expectedFreezeId?: string | null;
  readonly expectedFreezeGeneration?: number | null;
  /** Historical sessions without freeze (explicit legacy branch). */
  readonly allowLegacyWithoutFreeze?: boolean;
  readonly onProgress?: ((snapshot: ExportPrepDrainResult) => void) | undefined;
  /** Cancel this observer only; shared drain continues for other observers. */
  readonly signal?: AbortSignal | undefined;
}

type DrainObserver = {
  readonly id: number;
  readonly deadlineAt: number;
  readonly onProgress?: ((snapshot: ExportPrepDrainResult) => void) | undefined;
  cancelled: boolean;
  timer: ReturnType<typeof setTimeout> | null;
  resolve: (result: ExportPrepDrainResult) => void;
  abortHandler: (() => void) | null;
};

type SharedDrainWork = {
  readonly key: string;
  readonly sessionId: string;
  readonly startedAt: number;
  readonly pollMs: number;
  readonly producerBarrierCompleted: boolean;
  readonly expectedFreezeId: string | null;
  readonly expectedFreezeGeneration: number | null;
  readonly allowLegacyWithoutFreeze: boolean;
  readonly reason: ExportPrepEnsureReason;
  observers: Set<DrainObserver>;
  latest: ExportPrepDrainResult | null;
  terminal: ExportPrepDrainResult | null;
  running: boolean;
  wake: (() => void) | null;
  unsub: (() => void) | null;
  pollTimer: ReturnType<typeof setTimeout> | null;
};

/**
 * Durable producer-consumer for local ZIP export preparation.
 * Does not block MediaStore capture; one worker by default.
 */
export class ExportPrepQueue {
  private workers = 0;
  private maxWorkers: number;
  private maxObservedWorkers = 0;
  private readonly warningPendingThreshold: number;
  private readonly maxExportUncompressedBytes: number;
  private stopped = false;
  private readonly listeners = new Set<ExportPrepListener>();
  private preferredSessionId: string | null = null;
  private tickScheduled = false;
  private lastBackpressureWarnedAt = 0;
  private readonly drainWaiters = new Map<string, SharedDrainWork>();
  private nextObserverId = 1;
  /** Sessions blocked from claiming/processing (cancel/drain/purge). */
  private readonly cancelledSessions = new Set<string>();
  private readonly activeSessionWorkers = new Map<string, number>();
  /** Monotonic per-session jobs mutation counter for snapshot fencing. */
  private readonly sessionJobsRevision = new Map<string, number>();
  private stageObserver: ExportPrepStageObserver | null = null;
  readonly metrics = {
    jobsCompleted: 0,
    jobsFailed: 0,
    scansExecuted: 0,
    scansSkippedReadyDraft: 0,
    fenceLost: 0,
  };

  constructor(private readonly deps: ExportPrepQueueDeps) {
    this.maxWorkers = Math.max(1, Math.min(2, deps.maxWorkers ?? 1));
    this.warningPendingThreshold = Math.max(1, deps.warningPendingThreshold ?? 150);
    this.maxExportUncompressedBytes = deps.maxExportUncompressedBytes ?? 480 * 1024 * 1024;
  }

  /** Bounded scanner/prep concurrency: strictly 1 or 2. */
  setMaxWorkers(n: number): void {
    if (n !== 1 && n !== 2) {
      throw Object.assign(new Error('EXPORT_PREP_MAX_WORKERS_INVALID'), {
        code: 'EXPORT_PREP_MAX_WORKERS_INVALID',
        detail: `maxWorkers must be 1 or 2, got ${n}`,
      });
    }
    this.maxWorkers = n;
    this.scheduleTick();
  }

  getMaxWorkers(): 1 | 2 {
    return this.maxWorkers as 1 | 2;
  }

  getActiveWorkers(): number {
    return this.workers;
  }

  getMaxObservedWorkers(): number {
    return this.maxObservedWorkers;
  }

  /** In-flight processJob count for a session (snapshot fencing). */
  getActiveSessionWorkers(sessionId: string): number {
    return this.activeSessionWorkers.get(sessionId) ?? 0;
  }

  /** Current jobs mutation revision (bumped on create/requeue/invalidate). */
  getSessionJobsRevision(sessionId: string): number {
    return this.sessionJobsRevision.get(sessionId) ?? 0;
  }

  private bumpSessionJobsRevision(sessionId: string): number {
    const next = (this.sessionJobsRevision.get(sessionId) ?? 0) + 1;
    this.sessionJobsRevision.set(sessionId, next);
    return next;
  }

  /** Debug/benchmark only — null clears. No effect on production behavior when unset. */
  setStageObserver(observer: ExportPrepStageObserver | null | undefined): void {
    this.stageObserver = observer ?? null;
  }

  private observeStage(
    event: Parameters<ExportPrepStageObserver['onStage']>[0],
  ): void {
    if (!this.stageObserver) return;
    try {
      this.stageObserver.onStage(event);
    } catch {
      // never break prep for observer errors
    }
  }

  private monoNow(): number {
    const p = (globalThis as { performance?: { now(): number } }).performance;
    return typeof p?.now === 'function' ? p.now() : Date.now();
  }

  subscribe(listener: ExportPrepListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(sessionId: string | null, counts: ExportPrepCounts): void {
    for (const l of this.listeners) {
      try {
        l(sessionId, counts);
      } catch {
        // ignore listener errors
      }
    }
  }

  async getCounts(sessionId: string): Promise<ExportPrepCounts> {
    return this.deps.prepRepo.countsForSession(sessionId);
  }

  getMaxExportUncompressedBytes(): number {
    return this.maxExportUncompressedBytes;
  }

  async recoverOnBootstrap(): Promise<void> {
    // Bounded recovery only: requeue interrupted in-flight jobs. Full historical backfill
    // runs on REVIEW_OPEN / FINISH / EXPORT_PREFLIGHT — never scan all photos in the DB here.
    const n = await this.deps.prepRepo.recoverInterrupted();
    if (n > 0) {
      this.deps.logger?.info('export_prep', {
        code: 'EXPORT_PREP_BOOTSTRAP_RECOVERY',
        reason: 'RECOVERY',
        recovered: n,
      });
      this.deps.logger?.info('export_prep', {
        code: 'EXPORT_PREP_RECOVERY_RESUMED',
        recovered: n,
      });
    }
    this.scheduleTick();
  }

  /**
   * Ensure one durable job per eligible stable photo (session or active freeze).
   * Idempotent; safe for historical sessions without prep rows.
   * Does not weaken lease fencing — never touches in-flight jobs with a valid lease.
   *
   * Phase 3B: EXPORT_PREFLIGHT READY completeness uses **light** validation
   * (uri/name/size/sha-format/on-disk size). Cryptographic strong rehash remains
   * mandatory once at packaging (`resolveExportPhotosFromStaging`). Optional
   * `session`+`photos` avoid re-listing canonical export photos when export already
   * loaded them; jobs are batched via `listForSession` (no N× getByPhotoId).
   */
  async ensureJobsForEligiblePhotos(
    sessionId: string,
    options?: {
      readonly reason?: ExportPrepEnsureReason;
      readonly session?: CaptureSessionRow;
      readonly photos?: readonly CapturePhotoRow[];
    },
  ): Promise<EnsureExportPrepJobsResult> {
    const reason = options?.reason ?? 'RECOVERY';
    const started = Date.now();
    const base = emptyEnsureExportPrepJobsResult(sessionId, reason);
    const partialErrors: string[] = [];

    let session = options?.session ?? null;
    let photos = options?.photos ?? null;
    const reusedCanonicalPhotos = session != null && photos != null;
    if (!reusedCanonicalPhotos) {
      const listed = await listCanonicalExportPhotos(this.deps.captureRepo, sessionId);
      session = listed.session;
      photos = listed.photos;
    }
    if (!session) {
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_BACKFILL_SESSION_MISSING',
        sessionId,
        reason,
      });
      return { ...base, durationMs: Date.now() - started, partialErrors: ['SESSION_MISSING'] };
    }

    const eligible = selectEligibleExportPrepPhotos(photos!);
    const nonProcessable = selectNonProcessableExportPhotos(photos!);
    // Phase 3B: never double-strong. EXPORT_PREFLIGHT used to strong-validate every
    // READY job, then packaging strong-validated again. Completeness gate stays light;
    // packaging keeps the single native rehash integrity boundary.
    const readyMode: ReadyValidationMode = 'light';
    let existingJobs = 0;
    let createdJobs = 0;
    let requeuedJobs = 0;
    let invalidatedReadyJobs = 0;
    let excludedJobs = 0;
    let missingSourcePhotos = 0;
    let readyValidatedCount = 0;

    const jobsByPhoto = new Map<string, ExportPrepJobRow>();
    try {
      const listedJobs = await this.deps.prepRepo.listForSession(sessionId);
      for (const j of listedJobs) {
        jobsByPhoto.set(j.capture_photo_id, j);
      }
    } catch (error) {
      partialErrors.push(
        `list_jobs:${error instanceof Error ? error.message : String(error)}`,
      );
    }
    const batchedJobLookup = true;

    for (const photo of nonProcessable) {
      try {
        const existing = jobsByPhoto.get(photo.id) ?? null;
        if (existing && existing.status !== 'EXCLUDED') {
          await this.deps.prepRepo.markExcluded(photo.id);
          excludedJobs += 1;
        } else if (existing?.status === 'EXCLUDED') {
          existingJobs += 1;
        }
      } catch (error) {
        partialErrors.push(
          `exclude:${photo.id}:${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    for (const photo of eligible) {
      try {
        if (!photo.uri) {
          missingSourcePhotos += 1;
          partialErrors.push(`missing_uri:${photo.id}`);
          continue;
        }

        const existing = jobsByPhoto.get(photo.id) ?? null;

        if (existing?.status === 'READY') {
          readyValidatedCount += 1;
          const readyCheck = await validateReadyStaging(existing, readyMode);
          if (readyCheck.ok) {
            existingJobs += 1;
            continue;
          }
          await this.deps.prepRepo.invalidateReady(
            photo.id,
            `EXPORT_PREP_READY_INVALID:${readyCheck.failure ?? 'UNKNOWN'}`,
            'READY inválido tras validación de staging',
          );
          invalidatedReadyJobs += 1;
          this.bumpSessionJobsRevision(sessionId);
          // fall through to requeue after invalidation
        } else if (existing?.status === 'FAILED_TERMINAL') {
          existingJobs += 1;
          continue;
        } else if (existing?.status === 'EXCLUDED') {
          existingJobs += 1;
          continue;
        } else if (
          existing &&
          (existing.status === 'PREPARING' ||
            existing.status === 'SCANNING' ||
            existing.status === 'VALIDATING')
        ) {
          const now = new Date().toISOString();
          const leaseOk =
            existing.lease_token != null &&
            existing.lease_expires_at != null &&
            existing.lease_expires_at > now;
          if (leaseOk) {
            existingJobs += 1;
            continue;
          }
          // Expired lease: CAS requeue via enqueueIdempotent.
        } else if (existing?.status === 'FAILED_RETRYABLE') {
          existingJobs += 1;
          continue;
        } else if (existing?.status === 'QUEUED') {
          existingJobs += 1;
          continue;
        }

        // Need a durable job — require readable source unless we just invalidated READY
        // (invalidate cleared staging; source must still be readable to requeue).
        const needsSource =
          reason === 'FINISH' || reason === 'REVIEW_OPEN' || reason === 'EXPORT_PREFLIGHT';
        if (needsSource && !(await sourceUriIsReadable(photo.uri))) {
          missingSourcePhotos += 1;
          partialErrors.push(`missing_source:${photo.id}`);
          continue;
        }

        const seq = photo.sequence_number ?? 0;
        const exportFileName =
          seq > 0 ? exportPhotoFileName(photo.id, seq, photo.display_name) : null;
        const fingerprint = hashPreparedMetaSha256({
          uri: photo.uri,
          bytes: photo.size ?? 0,
          width: photo.width ?? 0,
          height: photo.height ?? 0,
        });
        const result = await this.deps.prepRepo.enqueueIdempotent({
          capturePhotoId: photo.id,
          captureSessionId: sessionId,
          sourceUri: photo.uri,
          sourceFingerprint: fingerprint,
          exportFileName,
        });
        if (result.created) {
          createdJobs += 1;
          this.bumpSessionJobsRevision(sessionId);
        } else if (result.requeued) {
          requeuedJobs += 1;
          this.bumpSessionJobsRevision(sessionId);
        } else {
          existingJobs += 1;
        }
      } catch (error) {
        partialErrors.push(
          `photo:${photo.id}:${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    this.preferredSessionId = sessionId;
    this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
    // EXPORT_PREFLIGHT with a stable READY snapshot must not kick workers
    // that could mutate other-session state mid-export; still schedule when
    // ensure created/requeued work that needs processing.
    const snapshotJobs = [...jobsByPhoto.values()];
    const activeWorkersForSession = this.activeSessionWorkers.get(sessionId) ?? 0;
    const attachSnapshot = canAttachJobsSnapshot({
      createdJobs,
      requeuedJobs,
      invalidatedReadyJobs,
      activeWorkersForSession,
      jobs: snapshotJobs,
    });
    if (!attachSnapshot || reason !== 'EXPORT_PREFLIGHT') {
      this.scheduleTick();
    }

    const result: EnsureExportPrepJobsResult = {
      sessionId,
      reason,
      eligiblePhotos: eligible.length,
      existingJobs,
      createdJobs,
      requeuedJobs,
      invalidatedReadyJobs,
      excludedJobs,
      missingSourcePhotos,
      partialErrors,
      durationMs: Date.now() - started,
      readyValidationMode: readyMode,
      readyValidatedCount,
      reusedCanonicalPhotos,
      batchedJobLookup,
      ...(attachSnapshot
        ? {
            jobsSnapshot: snapshotJobs,
            jobsSnapshotToken: buildJobsSnapshotToken(snapshotJobs),
            jobsSnapshotSessionId: sessionId,
            activeWorkersAtSnapshot: activeWorkersForSession,
            jobsSnapshotRevision: this.getSessionJobsRevision(sessionId),
          }
        : {}),
    };
    this.deps.logger?.info('export_prep', {
      code: 'EXPORT_PREP_BACKFILL',
      sessionId,
      reason,
      eligiblePhotos: result.eligiblePhotos,
      existingJobs: result.existingJobs,
      createdJobs: result.createdJobs,
      requeuedJobs: result.requeuedJobs,
      invalidatedReadyJobs: result.invalidatedReadyJobs,
      excludedJobs: result.excludedJobs,
      missingSourcePhotos: result.missingSourcePhotos,
      partialErrorCount: partialErrors.length,
      durationMs: result.durationMs,
      readyValidationMode: result.readyValidationMode,
      readyValidatedCount: result.readyValidatedCount,
      reusedCanonicalPhotos: result.reusedCanonicalPhotos,
      batchedJobLookup: result.batchedJobLookup,
      jobsSnapshotAttached: Boolean(result.jobsSnapshot),
      jobsSnapshotToken: result.jobsSnapshotToken ?? null,
      activeWorkersAtSnapshot: result.activeWorkersAtSnapshot ?? null,
    });
    return result;
  }

  private async isReadyJobComplete(job: ExportPrepJobRow): Promise<boolean> {
    return (await validateReadyStaging(job, 'light')).ok;
  }

  async enqueueStablePhoto(sessionId: string, photoId: string): Promise<void> {
    if (this.stopped) return;
    const photo = await this.deps.captureRepo.getPhotoById(photoId);
    if (!photo || photo.capture_session_id !== sessionId) {
      return;
    }
    if (photo.status === 'excluded' || photo.status === 'rejected') {
      await this.deps.prepRepo.markExcluded(photoId);
      return;
    }
    if (photo.status !== 'stable') {
      return;
    }

    const counts = await this.deps.prepRepo.countsForSession(sessionId);
    if (counts.pending >= this.warningPendingThreshold) {
      const now = Date.now();
      if (now - this.lastBackpressureWarnedAt > 5_000) {
        this.lastBackpressureWarnedAt = now;
        this.deps.logger?.warn('export_prep', {
          code: 'EXPORT_PREP_BACKPRESSURE_WARNING',
          sessionId,
          pending: counts.pending,
          warningPendingThreshold: this.warningPendingThreshold,
        });
      }
    }

    const seq = photo.sequence_number ?? 0;
    const exportFileName =
      seq > 0 ? exportPhotoFileName(photo.id, seq, photo.display_name) : null;
    const fingerprint = hashPreparedMetaSha256({
      uri: photo.uri,
      bytes: photo.size ?? 0,
      width: photo.width ?? 0,
      height: photo.height ?? 0,
    });

    const existing = await this.deps.prepRepo.getByPhotoId(photoId);
    if (existing?.status === 'READY' && (await this.isReadyJobComplete(existing))) {
      this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
      return;
    }
    if (existing?.status === 'READY') {
      await this.deps.prepRepo.invalidateReady(
        photoId,
        'EXPORT_PREP_STAGING_MISSING',
        'Archivo staged ausente tras reopen',
      );
      this.bumpSessionJobsRevision(sessionId);
    }

    const result = await this.deps.prepRepo.enqueueIdempotent({
      capturePhotoId: photoId,
      captureSessionId: sessionId,
      sourceUri: photo.uri,
      sourceFingerprint: fingerprint,
      exportFileName,
    });
    this.deps.logger?.info('export_prep', {
      code: 'EXPORT_PREP_ENQUEUE_STABLE',
      reason: 'PHOTO_STABLE',
      sessionId,
      capture_photo_id: photoId,
      created: result.created,
      status: result.job.status,
    });
    this.preferredSessionId = sessionId;
    this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
    this.scheduleTick();
  }

  async markPhotoExcluded(photoId: string): Promise<void> {
    await this.deps.prepRepo.markExcluded(photoId);
    const job = await this.deps.prepRepo.getByPhotoId(photoId);
    if (job) {
      this.emit(
        job.capture_session_id,
        await this.deps.prepRepo.countsForSession(job.capture_session_id),
      );
    }
  }

  async retryPhoto(photoId: string): Promise<void> {
    await this.deps.prepRepo.requeueFailed(photoId);
    const job = await this.deps.prepRepo.getByPhotoId(photoId);
    if (job) {
      this.preferredSessionId = job.capture_session_id;
      this.emit(
        job.capture_session_id,
        await this.deps.prepRepo.countsForSession(job.capture_session_id),
      );
    }
    this.scheduleTick();
  }

  async retryFailedForSession(sessionId: string): Promise<number> {
    const n = await this.deps.prepRepo.requeueAllFailedForSession(sessionId);
    this.preferredSessionId = sessionId;
    this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
    this.scheduleTick();
    return n;
  }

  /**
   * Phase 3 drain: ensure jobs after freeze, then observe until exportable,
   * terminal-complete, structural failure, or per-observer timeout.
   * Shared work is keyed by session+expected freeze; observers keep independent
   * progress callbacks and deadlines.
   */
  async waitUntilExportable(
    sessionId: string,
    options: WaitUntilExportableOptions,
  ): Promise<ExportPrepDrainResult> {
    if (typeof options.producerBarrierCompleted !== 'boolean') {
      throw new Error(
        'waitUntilExportable requires explicit producerBarrierCompleted (no default true)',
      );
    }
    const pollMs = Math.max(200, options.pollMs ?? 500);
    const timeoutMs = options.timeoutMs ?? 10 * 60_000;
    const reason = options.reason ?? 'FINISH';
    const expectedFreezeId =
      options.expectedFreezeId === undefined ? null : options.expectedFreezeId;
    const expectedFreezeGeneration =
      options.expectedFreezeGeneration === undefined
        ? null
        : options.expectedFreezeGeneration;
    const allowLegacyWithoutFreeze = options.allowLegacyWithoutFreeze === true;
    // Security invariants must be part of the shared-work key so incompatible
    // callers never share producerBarrierCompleted / legacy policy.
    const key = [
      sessionId,
      expectedFreezeId ?? 'nofreeze',
      expectedFreezeGeneration ?? 'nagen',
      options.producerBarrierCompleted ? 'barrier1' : 'barrier0',
      allowLegacyWithoutFreeze ? 'legacy1' : 'legacy0',
    ].join('|');

    let shared = this.drainWaiters.get(key);
    if (!shared) {
      shared = {
        key,
        sessionId,
        startedAt: Date.now(),
        pollMs,
        producerBarrierCompleted: options.producerBarrierCompleted,
        expectedFreezeId,
        expectedFreezeGeneration,
        allowLegacyWithoutFreeze,
        reason,
        observers: new Set(),
        latest: null,
        terminal: null,
        running: false,
        wake: null,
        unsub: null,
        pollTimer: null,
      };
      this.drainWaiters.set(key, shared);
      void this.runSharedDrain(shared);
    }

    return new Promise<ExportPrepDrainResult>((resolve) => {
      const observer: DrainObserver = {
        id: this.nextObserverId++,
        deadlineAt: Date.now() + timeoutMs,
        onProgress: options.onProgress,
        cancelled: false,
        timer: null,
        resolve,
        abortHandler: null,
      };
      shared!.observers.add(observer);

      const clearObserverTimer = () => {
        if (observer.timer) {
          clearTimeout(observer.timer);
          observer.timer = null;
        }
      };

      if (options.signal) {
        const onAbort = () => {
          if (observer.cancelled) return;
          clearObserverTimer();
          observer.cancelled = true;
          shared!.observers.delete(observer);
          const base =
            shared!.latest ??
            emptyExportPrepDrainResult(sessionId, {
              producerBarrierCompleted: options.producerBarrierCompleted,
              timedOut: true,
              durationMs: Date.now() - shared!.startedAt,
            });
          resolve({ ...base, timedOut: true, exportable: false });
        };
        if (options.signal.aborted) {
          onAbort();
          return;
        }
        observer.abortHandler = onAbort;
        options.signal.addEventListener('abort', onAbort, { once: true });
      }

      if (shared!.terminal) {
        this.deliverToObserver(shared!, observer, shared!.terminal);
        return;
      }

      const tickObserver = () => {
        if (observer.cancelled || !shared) return;
        if (shared.terminal) {
          this.deliverToObserver(shared, observer, shared.terminal);
          return;
        }
        if (Date.now() >= observer.deadlineAt) {
          const base =
            shared.latest ??
            emptyExportPrepDrainResult(sessionId, {
              producerBarrierCompleted: options.producerBarrierCompleted,
              timedOut: true,
              durationMs: Date.now() - shared.startedAt,
            });
          const timedOut: ExportPrepDrainResult = {
            ...base,
            timedOut: true,
            exportable: false,
            durationMs: Date.now() - shared.startedAt,
          };
          this.deps.logger?.warn('export_prep', {
            code: 'EXPORT_PREP_OBSERVER_TIMEOUT',
            sessionId,
            observerId: observer.id,
            ready: timedOut.ready,
            totalEligible: timedOut.totalEligible,
            durationMs: timedOut.durationMs,
          });
          this.deliverToObserver(shared, observer, timedOut);
          return;
        }
        if (shared.latest) {
          try {
            observer.onProgress?.(shared.latest);
          } catch {
            // ignore observer progress errors
          }
        }
        const remaining = Math.max(50, observer.deadlineAt - Date.now());
        clearObserverTimer();
        observer.timer = setTimeout(tickObserver, Math.min(pollMs, remaining));
      };
      clearObserverTimer();
      observer.timer = setTimeout(tickObserver, 0);
    });
  }

  private deliverToObserver(
    shared: SharedDrainWork,
    observer: DrainObserver,
    result: ExportPrepDrainResult,
  ): void {
    if (observer.cancelled) return;
    observer.cancelled = true;
    if (observer.timer) {
      clearTimeout(observer.timer);
      observer.timer = null;
    }
    if (observer.abortHandler) {
      // Listener is once; drop reference.
      observer.abortHandler = null;
    }
    shared.observers.delete(observer);
    try {
      observer.onProgress?.(result);
    } catch {
      // ignore
    }
    observer.resolve(result);
    if (shared.observers.size === 0 && shared.terminal) {
      this.cleanupSharedDrain(shared);
    }
  }

  private cleanupSharedDrain(shared: SharedDrainWork): void {
    if (shared.pollTimer) {
      clearTimeout(shared.pollTimer);
      shared.pollTimer = null;
    }
    shared.unsub?.();
    shared.unsub = null;
    this.drainWaiters.delete(shared.key);
  }

  private async runSharedDrain(shared: SharedDrainWork): Promise<void> {
    if (shared.running) return;
    shared.running = true;
    const {
      sessionId,
      producerBarrierCompleted,
      expectedFreezeId,
      expectedFreezeGeneration,
      allowLegacyWithoutFreeze,
      reason,
      pollMs,
    } = shared;

    this.deps.logger?.info('export_prep', {
      code: 'EXPORT_PREP_FINISH_STARTED',
      sessionId,
      reason,
      expectedFreezeId: expectedFreezeId ?? null,
      expectedFreezeGeneration: expectedFreezeGeneration ?? null,
    });

    let backfillPartialErrors: string[] = [];
    let missingSourcePhotos = 0;

    const applyBackfill = async (r: ExportPrepEnsureReason) => {
      const ensured = await this.ensureJobsForEligiblePhotos(sessionId, { reason: r });
      backfillPartialErrors = [...ensured.partialErrors];
      missingSourcePhotos = ensured.missingSourcePhotos;
      this.deps.logger?.info('export_prep', {
        code: 'EXPORT_PREP_BACKFILL_COMPLETE',
        sessionId,
        reason: r,
        eligiblePhotos: ensured.eligiblePhotos,
        createdJobs: ensured.createdJobs,
        missingSourcePhotos: ensured.missingSourcePhotos,
        partialErrorCount: ensured.partialErrors.length,
        durationMs: ensured.durationMs,
      });
      return ensured;
    };

    const finishTerminal = (result: ExportPrepDrainResult) => {
      shared.terminal = result;
      shared.latest = result;
      for (const obs of [...shared.observers]) {
        this.deliverToObserver(shared, obs, result);
      }
      this.cleanupSharedDrain(shared);
    };

    try {
      await applyBackfill(reason);
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const snap = await this.snapshotDrain(sessionId, {
          producerBarrierCompleted,
          timedOut: false,
          durationMs: Date.now() - shared.startedAt,
          expectedFreezeId,
          expectedFreezeGeneration,
          allowLegacyWithoutFreeze,
          backfillPartialErrors,
          missingSourcePhotos,
        });
        if (snap.missingJobs === 0 || snap.structuralError) break;
        await applyBackfill(reason);
      }

      this.preferredSessionId = sessionId;
      this.scheduleTick();

      shared.unsub = this.subscribe((sid) => {
        if (sid === sessionId || sid == null) shared.wake?.();
      });

      // Cap shared work to 30 minutes absolute; observers may exit earlier.
      const sharedDeadline = shared.startedAt + 30 * 60_000;
      let continuePolling = true;
      while (continuePolling) {
        if (!this.stopped) this.scheduleTick();
        const snap = await this.snapshotDrain(sessionId, {
          producerBarrierCompleted,
          timedOut: false,
          durationMs: Date.now() - shared.startedAt,
          expectedFreezeId,
          expectedFreezeGeneration,
          allowLegacyWithoutFreeze,
          backfillPartialErrors,
          missingSourcePhotos,
        });
        shared.latest = snap;
        for (const obs of shared.observers) {
          if (!obs.cancelled) {
            try {
              obs.onProgress?.(snap);
            } catch {
              // ignore
            }
          }
        }

        this.deps.logger?.info('export_prep', {
          code: 'EXPORT_PREP_DRAIN_PROGRESS',
          sessionId,
          freezeId: snap.freezeId,
          freezeGeneration: snap.freezeGeneration,
          totalEligible: snap.totalEligible,
          ready: snap.ready,
          pending: snap.queued + snap.processing,
          failedRetryable: snap.failedRetryable,
          failedTerminal: snap.failedTerminal,
          missingJobs: snap.missingJobs,
          structuralError: snap.structuralError,
          durationMs: snap.durationMs,
        });

        if (snap.structuralError) {
          this.deps.logger?.warn('export_prep', {
            code:
              snap.structuralError === 'SESSION_MISSING'
                ? 'EXPORT_PREP_SESSION_MISSING'
                : snap.structuralError === 'FREEZE_CHANGED'
                  ? 'EXPORT_PREP_FREEZE_CHANGED'
                  : 'EXPORT_PREP_DRAIN_FAILED',
            sessionId,
            structuralError: snap.structuralError,
          });
          finishTerminal(snap);
          return;
        }

        if (snap.exportable) {
          this.deps.logger?.info('export_prep', {
            code: 'EXPORT_PREP_DRAIN_READY',
            sessionId,
            freezeId: snap.freezeId,
            totalEligible: snap.totalEligible,
            ready: snap.ready,
            durationMs: snap.durationMs,
          });
          finishTerminal(snap);
          return;
        }

        if (
          snap.missingJobs === 0 &&
          snap.queued === 0 &&
          snap.processing === 0 &&
          snap.failedRetryable === 0 &&
          snap.failedTerminal > 0 &&
          snap.ready + snap.failedTerminal === snap.totalEligible
        ) {
          this.deps.logger?.info('export_prep', {
            code: 'EXPORT_PREP_DRAIN_FAILED',
            sessionId,
            failedTerminal: snap.failedTerminal,
            ready: snap.ready,
            durationMs: snap.durationMs,
          });
          finishTerminal(snap);
          return;
        }

        if (
          snap.missingJobs > 0 &&
          snap.queued === 0 &&
          snap.processing === 0 &&
          Date.now() - shared.startedAt > 2_000
        ) {
          await applyBackfill('RECOVERY');
          const after = await this.snapshotDrain(sessionId, {
            producerBarrierCompleted,
            timedOut: false,
            durationMs: Date.now() - shared.startedAt,
            expectedFreezeId,
            expectedFreezeGeneration,
            allowLegacyWithoutFreeze,
            backfillPartialErrors,
            missingSourcePhotos,
          });
          if (
            after.structuralError ||
            (after.missingJobs > 0 && after.queued === 0 && after.processing === 0)
          ) {
            finishTerminal(after);
            return;
          }
        }

        // stop() ends workers; still allow a final snapshot above, then exit drain loop.
        if (this.stopped || Date.now() >= sharedDeadline) {
          continuePolling = false;
          break;
        }

        if (shared.observers.size === 0) {
          await new Promise<void>((r) => {
            shared.pollTimer = setTimeout(r, pollMs);
          });
          if (shared.observers.size === 0 || this.stopped) {
            finishTerminal(snap);
            return;
          }
          continue;
        }

        await new Promise<void>((resolve) => {
          let settled = false;
          const done = () => {
            if (settled) return;
            settled = true;
            shared.wake = null;
            if (shared.pollTimer) {
              clearTimeout(shared.pollTimer);
              shared.pollTimer = null;
            }
            resolve();
          };
          shared.wake = done;
          shared.pollTimer = setTimeout(done, pollMs);
        });
      }

      const timedOut = await this.snapshotDrain(sessionId, {
        producerBarrierCompleted,
        timedOut: !this.stopped,
        durationMs: Date.now() - shared.startedAt,
        expectedFreezeId,
        expectedFreezeGeneration,
        allowLegacyWithoutFreeze,
        backfillPartialErrors,
        missingSourcePhotos,
      });
      // If already exportable on the final look (e.g. stop after READY mark), prefer that.
      if (timedOut.exportable) {
        finishTerminal({ ...timedOut, timedOut: false });
        return;
      }
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_DRAIN_TIMEOUT',
        sessionId,
        durationMs: timedOut.durationMs,
      });
      finishTerminal({ ...timedOut, timedOut: true, exportable: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const lower = message.toLowerCase();
      let structuralError: ExportPrepStructuralError = 'DRAIN_FAILED';
      if (
        lower.includes('no such table') ||
        lower.includes('sqlite') ||
        lower.includes('database')
      ) {
        structuralError = 'DATABASE_ERROR';
      } else if (
        lower.includes('enoent') ||
        lower.includes('eacces') ||
        lower.includes('storage') ||
        lower.includes('file')
      ) {
        structuralError = 'STORAGE_ERROR';
      } else if (
        message.includes('SESSION_MISSING') ||
        (lower.includes('sesión') && lower.includes('no'))
      ) {
        structuralError = 'SESSION_MISSING';
      }
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_DRAIN_FAILED',
        sessionId,
        structuralError,
        message,
      });
      finishTerminal(
        emptyExportPrepDrainResult(sessionId, {
          producerBarrierCompleted,
          timedOut: false,
          exportable: false,
          structuralError,
          durationMs: Date.now() - shared.startedAt,
          backfillPartialErrors: [...backfillPartialErrors, message],
        }),
      );
    }
  }

  async snapshotDrain(
    sessionId: string,
    meta: {
      readonly producerBarrierCompleted: boolean;
      readonly timedOut: boolean;
      readonly durationMs: number;
      readonly expectedFreezeId?: string | null | undefined;
      readonly expectedFreezeGeneration?: number | null | undefined;
      readonly allowLegacyWithoutFreeze?: boolean;
      readonly backfillPartialErrors?: readonly string[];
      readonly missingSourcePhotos?: number;
    },
  ): Promise<ExportPrepDrainResult> {
    const { session, photos } = await listCanonicalExportPhotos(
      this.deps.captureRepo,
      sessionId,
    );

    if (!session) {
      return emptyExportPrepDrainResult(sessionId, {
        sessionExists: false,
        canonicalSnapshotAvailable: false,
        producerBarrierCompleted: meta.producerBarrierCompleted,
        structuralError: 'SESSION_MISSING',
        timedOut: meta.timedOut,
        durationMs: meta.durationMs,
        backfillPartialErrors: meta.backfillPartialErrors ?? [],
        missingSourcePhotos: meta.missingSourcePhotos ?? 0,
        exportable: false,
      });
    }

    const freezeId = session.active_freeze_id;
    const freezeGeneration = session.capture_freeze_generation ?? null;
    const expectedFreezeId = meta.expectedFreezeId;
    const expectedFreezeGeneration = meta.expectedFreezeGeneration;
    const allowLegacy = meta.allowLegacyWithoutFreeze === true;

    let structuralError: ExportPrepStructuralError = null;
    if (freezeId == null && !allowLegacy) {
      // Modern / prep-required path: missing freeze is never treated as legacy.
      structuralError = 'FREEZE_MISSING';
    } else if (
      expectedFreezeId != null &&
      freezeId != null &&
      expectedFreezeId !== freezeId
    ) {
      structuralError = 'FREEZE_CHANGED';
    } else if (
      expectedFreezeGeneration != null &&
      freezeGeneration != null &&
      expectedFreezeGeneration !== freezeGeneration
    ) {
      structuralError = 'FREEZE_CHANGED';
    }

    const eligible = selectEligibleExportPrepPhotos(photos);
    const jobs = await this.deps.prepRepo.listForSession(sessionId);
    const byId = new Map(jobs.map((j) => [j.capture_photo_id, j]));
    let ready = 0;
    let queued = 0;
    let processing = 0;
    let failedRetryable = 0;
    let failedTerminal = 0;
    let missingJobs = 0;
    let excluded = 0;
    for (const photo of eligible) {
      const job = byId.get(photo.id);
      if (!job) {
        missingJobs += 1;
        continue;
      }
      switch (job.status) {
        case 'READY':
          ready += 1;
          break;
        case 'QUEUED':
          queued += 1;
          break;
        case 'PREPARING':
        case 'SCANNING':
        case 'VALIDATING':
          processing += 1;
          break;
        case 'FAILED_RETRYABLE':
          failedRetryable += 1;
          break;
        case 'FAILED_TERMINAL':
          failedTerminal += 1;
          break;
        case 'EXCLUDED':
          excluded += 1;
          break;
        default:
          processing += 1;
          break;
      }
    }
    for (const photo of selectNonProcessableExportPhotos(photos)) {
      const job = byId.get(photo.id);
      if (job?.status === 'EXCLUDED') excluded += 1;
    }

    const backfillPartialErrors = meta.backfillPartialErrors ?? [];
    const missingSourcePhotos = meta.missingSourcePhotos ?? 0;
    const sessionMissingInBackfill = backfillPartialErrors.some(
      (e) => e === 'SESSION_MISSING' || e.includes('SESSION_MISSING'),
    );
    if (sessionMissingInBackfill) {
      structuralError = 'SESSION_MISSING';
    }
    // Missing sources surface as missingJobs / failed jobs — not a silent empty success.
    const hasBlockingBackfillErrors =
      sessionMissingInBackfill ||
      backfillPartialErrors.some((e) => e.startsWith('session:') || e.includes('STRUCTURAL'));

    const countsOk =
      missingJobs === 0 &&
      queued === 0 &&
      processing === 0 &&
      failedRetryable === 0 &&
      failedTerminal === 0 &&
      ready === eligible.length;

    const freezeOk =
      allowLegacy ||
      (freezeId != null &&
        (expectedFreezeId == null || expectedFreezeId === freezeId) &&
        (expectedFreezeGeneration == null ||
          expectedFreezeGeneration === freezeGeneration));

    const exportable =
      session != null &&
      structuralError == null &&
      meta.producerBarrierCompleted === true &&
      freezeOk &&
      !hasBlockingBackfillErrors &&
      countsOk;

    return {
      sessionId,
      sessionExists: true,
      canonicalSnapshotAvailable: true,
      freezeId,
      freezeGeneration,
      totalEligible: eligible.length,
      ready,
      queued,
      processing,
      failedRetryable,
      failedTerminal,
      missingJobs,
      excluded,
      timedOut: meta.timedOut,
      producerBarrierCompleted: meta.producerBarrierCompleted,
      structuralError,
      exportable: exportable && structuralError == null,
      durationMs: meta.durationMs,
      backfillPartialErrors,
      missingSourcePhotos,
    };
  }

  stop(): void {
    this.stopped = true;
    for (const shared of [...this.drainWaiters.values()]) {
      if (shared.pollTimer) clearTimeout(shared.pollTimer);
      shared.unsub?.();
      const terminal =
        shared.latest ??
        emptyExportPrepDrainResult(shared.sessionId, {
          producerBarrierCompleted: shared.producerBarrierCompleted,
          timedOut: true,
          exportable: false,
        });
      for (const obs of [...shared.observers]) {
        this.deliverToObserver(shared, obs, { ...terminal, timedOut: true, exportable: false });
      }
      this.drainWaiters.delete(shared.key);
    }
  }

  /** @deprecated use waitUntilExportable — Phase 3 drain */
  async waitUntilSettled(
    sessionId: string,
    options?: {
      readonly timeoutMs?: number;
      readonly pollMs?: number;
      readonly producerBarrierCompleted?: boolean;
    },
  ): Promise<{ readonly ok: boolean; readonly unresolved: number } & ExportPrepSettleResult> {
    const drain = await this.waitUntilExportable(sessionId, {
      ...(options?.timeoutMs !== undefined ? { timeoutMs: options.timeoutMs } : {}),
      ...(options?.pollMs !== undefined ? { pollMs: options.pollMs } : {}),
      producerBarrierCompleted: options?.producerBarrierCompleted === true,
      allowLegacyWithoutFreeze: true,
      reason: 'RECOVERY',
    });
    return {
      ok: drain.exportable,
      totalEligible: drain.totalEligible,
      ready: drain.ready,
      excluded: drain.excluded,
      failed: drain.failedTerminal + drain.failedRetryable,
      pending: drain.queued + drain.processing,
      missingJobs: drain.missingJobs,
      failedTerminal: drain.failedTerminal,
      failedRetryable: drain.failedRetryable,
      unresolved: drain.queued + drain.processing + drain.missingJobs + drain.failedRetryable,
    };
  }

  async evaluateExportability(sessionId: string): Promise<ExportPrepSettleResult> {
    const drain = await this.snapshotDrain(sessionId, {
      producerBarrierCompleted: false,
      timedOut: false,
      durationMs: 0,
      allowLegacyWithoutFreeze: true,
    });
    // evaluateExportability is a soft UI gate: use job counts only when session exists.
    // Full exportable still requires coordinator drain with barrier proof.
    const ok =
      drain.sessionExists &&
      drain.structuralError == null &&
      drain.missingJobs === 0 &&
      drain.queued === 0 &&
      drain.processing === 0 &&
      drain.failedRetryable === 0 &&
      drain.failedTerminal === 0 &&
      drain.ready === drain.totalEligible;
    return {
      ok,
      totalEligible: drain.totalEligible,
      ready: drain.ready,
      excluded: drain.excluded,
      failed: drain.failedTerminal + drain.failedRetryable,
      pending: drain.queued + drain.processing,
      missingJobs: drain.missingJobs,
      failedTerminal: drain.failedTerminal,
      failedRetryable: drain.failedRetryable,
    };
  }

  /**
   * Explicit session cleanup: durable jobs + staging files.
   * Share cancel must NOT call this — retention keeps staging until session purge.
   */
  async purgeSessionArtifacts(sessionId: string): Promise<void> {
    await this.deps.prepRepo.deleteForSession(sessionId);
    await deleteSessionExportStaging(sessionId);
  }

  /**
   * Stop admission of new work for session, release leases, wait for in-flight workers.
   * Physical delete is the caller's responsibility after this returns.
   */
  async cancelAndDrainSession(sessionId: string, timeoutMs = 30_000): Promise<void> {
    this.cancelledSessions.add(sessionId);
    await this.deps.prepRepo.releaseLeasesForSession(sessionId);
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const n = this.activeSessionWorkers.get(sessionId) ?? 0;
      if (n <= 0) break;
      await new Promise<void>((resolve) => setTimeout(resolve, 40));
    }
    this.cancelledSessions.delete(sessionId);
  }

  isSessionCancelled(sessionId: string): boolean {
    return this.cancelledSessions.has(sessionId);
  }

  /** Allow coordinators to wake the worker after requeue. */
  wake(): void {
    this.scheduleTick();
  }

  private scheduleTick(): void {
    if (this.stopped || this.tickScheduled) return;
    this.tickScheduled = true;
    queueMicrotask(() => {
      this.tickScheduled = false;
      void this.tick();
    });
  }

  private async tick(): Promise<void> {
    if (this.stopped) return;
    while (this.workers < this.maxWorkers) {
      let job = await this.deps.prepRepo.claimNext(this.preferredSessionId);
      if (!job && this.preferredSessionId) {
        job = await this.deps.prepRepo.claimNext(null);
      }
      if (!job) break;
      if (!job.lease_token) {
        this.deps.logger?.warn('error', {
          code: 'EXPORT_PREP_CLAIM_WITHOUT_LEASE',
          capture_photo_id: job.capture_photo_id,
        });
        break;
      }
      if (this.cancelledSessions.has(job.capture_session_id)) {
        await this.deps.prepRepo.releaseLeasesForSession(job.capture_session_id);
        continue;
      }
      this.workers += 1;
      this.maxObservedWorkers = Math.max(this.maxObservedWorkers, this.workers);
      const sid = job.capture_session_id;
      this.activeSessionWorkers.set(sid, (this.activeSessionWorkers.get(sid) ?? 0) + 1);
      void this.processJob(job).finally(() => {
        this.workers -= 1;
        const cur = this.activeSessionWorkers.get(sid) ?? 1;
        if (cur <= 1) this.activeSessionWorkers.delete(sid);
        else this.activeSessionWorkers.set(sid, cur - 1);
        this.scheduleTick();
      });
    }
  }

  private async processJob(job: ExportPrepJobRow): Promise<void> {
    const sessionId = job.capture_session_id;
    const leaseToken = job.lease_token;
    if (!leaseToken) {
      this.metrics.fenceLost += 1;
      return;
    }
    if (this.cancelledSessions.has(sessionId)) {
      return;
    }
    try {
      const photo = await this.deps.captureRepo.getPhotoById(job.capture_photo_id);
      if (!photo || photo.status === 'excluded' || photo.status === 'rejected') {
        // Exclusion invalidates lease; do not use fenced worker path.
        await this.deps.prepRepo.markExcluded(job.capture_photo_id);
        this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
        return;
      }

      const seq = photo.sequence_number;
      if (seq == null || seq <= 0) {
        throw Object.assign(new Error('EXPORT_PREP_MISSING_SEQUENCE'), {
          code: 'EXPORT_PREP_MISSING_SEQUENCE',
        });
      }
      const exportFileName =
        job.export_file_name || exportPhotoFileName(photo.id, seq, photo.display_name);

      await this.deps.prepRepo.renewLease(job.capture_photo_id, leaseToken, 120_000);

      const stageT0 = this.monoNow();
      const staged = await stageOriginalPhotoVersioned({
        sessionId,
        sourceUri: photo.uri,
        exportFileName,
        previousStagingUri: job.staging_uri,
      });
      this.observeStage({
        stage: 'staging_copy',
        photoId: photo.id,
        sequence: seq,
        monotonicStartMs: stageT0,
        durationMs: this.monoNow() - stageT0,
        inputBytes: photo.size ?? null,
        outputBytes: staged.sizeBytes,
        queueDepth: null,
        workerConcurrency: this.maxWorkers,
        executionContext: 'js',
        success: true,
        errorCode: null,
      });

      await this.deps.prepRepo.markScanning(job.capture_photo_id, leaseToken, {
        stagingUri: staged.stagingUri,
        exportFileName,
        sizeBytes: staged.sizeBytes,
        renewLeaseMs: 180_000,
      });

      const scanT0 = this.monoNow();
      await this.runCodeScanIfNeeded(photo, staged.stagingUri);
      this.observeStage({
        stage: 'local_scan',
        photoId: photo.id,
        sequence: seq,
        monotonicStartMs: scanT0,
        durationMs: this.monoNow() - scanT0,
        inputBytes: staged.sizeBytes,
        outputBytes: null,
        queueDepth: null,
        workerConcurrency: this.maxWorkers,
        executionContext: 'native',
        success: true,
        errorCode: null,
      });

      await this.deps.prepRepo.markValidating(job.capture_photo_id, leaseToken, 60_000);

      const draftRow = await this.lookupDraftInstrumented({
        sessionId,
        photoId: photo.id,
        sequence: seq,
        purpose: 'export_ready_check',
      });
      if (!isDraftExportReady(draftRow)) {
        throw Object.assign(new Error('EXPORT_PREP_DRAFT_NOT_READY'), {
          code: 'EXPORT_PREP_DRAFT_NOT_READY',
        });
      }

      let sha256: string;
      try {
        const hashT0 = this.monoNow();
        assertNativeDigestCapability();
        const hashed = await hashStagedFileSha256Detailed(staged.stagingUri);
        sha256 = hashed.sha256;
        this.observeStage({
          stage: 'staging_hash',
          photoId: photo.id,
          sequence: seq,
          monotonicStartMs: hashT0,
          durationMs: this.monoNow() - hashT0,
          inputBytes: hashed.bytesHashed,
          outputBytes: 64,
          queueDepth: null,
          workerConcurrency: this.maxWorkers,
          executionContext: 'native',
          success: true,
          errorCode: null,
          extras: {
            hashCount: 1,
            fullFileReadCount: 1,
            hashInputBytes: hashed.bytesHashed,
            hashExecutionContext: 'native',
            hashImplementation: 'native_stream',
            hashMode: 'native_file',
            hashSource: 'computed',
            bytesHashed: hashed.bytesHashed,
            digestReused: false,
            base64FullFileHashCount: 0,
          },
        });
      } catch (error) {
        const classified = classifyStagedDigestError(error);
        throw Object.assign(
          new Error(error instanceof Error ? error.message : 'EXPORT_PREP_HASH_FAILED'),
          {
            code:
              classified.failure === 'STAGING_DIGEST_UNAVAILABLE'
                ? 'EXPORT_PREP_DIGEST_UNAVAILABLE'
                : 'EXPORT_PREP_HASH_FAILED',
          },
        );
      }

      await this.deps.prepRepo.markReady(job.capture_photo_id, leaseToken, {
        stagingUri: staged.stagingUri,
        exportFileName,
        sizeBytes: staged.sizeBytes,
        sha256,
      });
      this.metrics.jobsCompleted += 1;
    } catch (error) {
      if (error instanceof ExportPrepFenceError) {
        this.metrics.fenceLost += 1;
        this.deps.logger?.warn('error', {
          code: 'EXPORT_PREP_FENCE_LOST',
          capture_photo_id: job.capture_photo_id,
          message: error.message,
        });
        this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
        return;
      }
      const code =
        error && typeof error === 'object' && 'code' in error
          ? String((error as { code: unknown }).code)
          : 'EXPORT_PREP_FAILED';
      const message = error instanceof Error ? error.message : String(error);
      try {
        await this.deps.prepRepo.markFailedFenced(
          job.capture_photo_id,
          leaseToken,
          code,
          message,
        );
      } catch (fenceErr) {
        this.metrics.fenceLost += 1;
        this.deps.logger?.warn('error', {
          code: 'EXPORT_PREP_FENCE_LOST',
          where: 'markFailedFenced',
          capture_photo_id: job.capture_photo_id,
          message: fenceErr instanceof Error ? fenceErr.message : String(fenceErr),
          original_error: message,
        });
        this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
        return;
      }
      this.metrics.jobsFailed += 1;
      this.deps.logger?.warn('error', {
        code,
        where: 'export_prep_job_failed',
        capture_photo_id: job.capture_photo_id,
        message,
      });
    }
    this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
  }

  /**
   * Timed draft lookup. `durationMs` covers only `getBySessionAndPhotoId` —
   * never `countsForSession` or other SQLite work.
   */
  private async lookupDraftInstrumented(input: {
    readonly sessionId: string;
    readonly photoId: string;
    readonly sequence: number | null;
    readonly purpose: DraftLookupPurpose;
  }): Promise<Awaited<
    ReturnType<typeof this.deps.draftRepo.getBySessionAndPhotoId>
  >['draft']> {
    const stageName =
      input.purpose === 'skip_scan_check'
        ? ('draft_lookup_pre_scan' as const)
        : ('draft_lookup_post_scan' as const);
    const draftT0 = this.monoNow();
    let draftRow: Awaited<
      ReturnType<typeof this.deps.draftRepo.getBySessionAndPhotoId>
    >['draft'] = null;
    let lookupExtras: {
      queryCount: number;
      rowsReturned: number;
      fullSessionRowsLoaded: number;
      lookupMode: string;
      lookupPurpose: DraftLookupPurpose;
      selectionRule: string | null;
      cacheHit: boolean;
      draftFound: boolean;
      draftReady: boolean;
    } = {
      queryCount: 1,
      rowsReturned: 0,
      fullSessionRowsLoaded: 0,
      lookupMode: 'direct_indexed_lookup',
      lookupPurpose: input.purpose,
      selectionRule: null,
      cacheHit: false,
      draftFound: false,
      draftReady: false,
    };
    let lookupErrorCode: string | null = null;
    let lookupSuccess = false;
    try {
      const lookup = await this.deps.draftRepo.getBySessionAndPhotoId(
        input.sessionId,
        input.photoId,
      );
      const durationMs = this.monoNow() - draftT0;
      draftRow = lookup.draft;
      lookupExtras = {
        queryCount: lookup.queryCount,
        rowsReturned: lookup.rowsMatched,
        fullSessionRowsLoaded: lookup.fullSessionRowsLoaded,
        lookupMode: lookup.lookupMode,
        lookupPurpose: input.purpose,
        selectionRule: lookup.selectionRule,
        cacheHit: false,
        draftFound: draftRow != null,
        draftReady: isDraftExportReady(draftRow),
      };
      lookupSuccess =
        input.purpose === 'skip_scan_check'
          ? true
          : isDraftExportReady(draftRow);
      lookupErrorCode =
        input.purpose === 'export_ready_check' && !isDraftExportReady(draftRow)
          ? 'EXPORT_PREP_DRAFT_NOT_READY'
          : null;
      const common = {
        photoId: input.photoId,
        sequence: input.sequence,
        monotonicStartMs: draftT0,
        durationMs,
        inputBytes: null as number | null,
        outputBytes: null as number | null,
        queueDepth: null as number | null,
        workerConcurrency: this.maxWorkers,
        executionContext: 'js' as const,
        success: lookupSuccess,
        errorCode: lookupErrorCode,
        extras: lookupExtras,
      };
      // Purpose-specific stage + legacy alias so gates/aggregators stay compatible.
      this.observeStage({ stage: stageName, ...common });
      this.observeStage({ stage: 'draft_lookup', ...common });
      return draftRow;
    } catch (error) {
      const durationMs = this.monoNow() - draftT0;
      const code =
        error && typeof error === 'object' && 'code' in error
          ? String((error as { code: unknown }).code)
          : 'DRAFT_LOOKUP_FAILED';
      lookupErrorCode = code;
      const common = {
        photoId: input.photoId,
        sequence: input.sequence,
        monotonicStartMs: draftT0,
        durationMs,
        inputBytes: null as number | null,
        outputBytes: null as number | null,
        queueDepth: null as number | null,
        workerConcurrency: this.maxWorkers,
        executionContext: 'js' as const,
        success: false,
        errorCode: lookupErrorCode,
        extras: lookupExtras,
      };
      this.observeStage({ stage: stageName, ...common });
      this.observeStage({ stage: 'draft_lookup', ...common });
      throw Object.assign(
        new Error(error instanceof Error ? error.message : 'DRAFT_LOOKUP_FAILED'),
        { code: lookupErrorCode },
      );
    }
  }

  private async runCodeScanIfNeeded(
    photo: {
      readonly id: string;
      readonly capture_session_id: string;
      readonly client_file_id: string | null;
      readonly upload_cancel_requested?: number;
      readonly sequence_number?: number | null;
    },
    stagedUri: string,
  ): Promise<void> {
    const strategy = this.deps.localCodeScan;
    if (!strategy || !this.deps.localCodeScanEnabled) {
      return;
    }
    const existing = await this.lookupDraftInstrumented({
      sessionId: photo.capture_session_id,
      photoId: photo.id,
      sequence: photo.sequence_number ?? null,
      purpose: 'skip_scan_check',
    });
    if (isDraftExportReady(existing)) {
      this.metrics.scansSkippedReadyDraft += 1;
      return;
    }

    const session = await this.deps.captureRepo.getSession(photo.capture_session_id);
    const sessionMode = normalizePreparationProcessingMode(session?.preparation_processing_mode);
    const processingMode = resolveLocalScanProcessingMode(sessionMode, true);
    let fingerprint: string;
    try {
      fingerprint = await hashPreparedFileSha256(stagedUri);
    } catch {
      fingerprint = hashPreparedMetaSha256({
        uri: stagedUri,
        bytes: 0,
        width: 0,
        height: 0,
      });
    }
    this.metrics.scansExecuted += 1;
    await strategy.execute({
      capturePhotoId: photo.id,
      captureSessionId: photo.capture_session_id,
      clientFileId: photo.client_file_id,
      preparedUri: stagedUri,
      preparedAssetFingerprint: fingerprint,
      processingMode,
      flagEnabled: true,
      cancelRequested: photo.upload_cancel_requested === 1,
      inventoryId: session?.inventory_id ?? null,
      aisleId: session?.aisle_id ?? null,
      recognitionContext: 'OFFLINE',
    });
  }
}

export function summarizeExportPrepForUi(
  photoCounts: { total: number; waiting: number; stable: number; errors: number; excluded: number },
  prep: ExportPrepCounts | null,
): string {
  if (!prep) {
    return `Detectadas: ${photoCounts.total} · Validando: ${photoCounts.waiting} · Estables: ${photoCounts.stable} · Error: ${photoCounts.errors} · Excluidas: ${photoCounts.excluded}`;
  }
  return (
    `Capturadas: ${photoCounts.total}` +
    ` · Estabilidad: ${photoCounts.waiting}` +
    ` · Prep pendientes: ${prep.queued}` +
    ` · Procesando: ${prep.processing}` +
    ` · Listas: ${prep.ready}` +
    ` · Fallidas: ${prep.failed}` +
    ` · Excluidas: ${photoCounts.excluded + prep.excluded}`
  );
}
