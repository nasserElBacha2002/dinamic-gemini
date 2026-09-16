import type { CaptureRepository } from '../../database/repositories/captureRepository';
import {
  ExportPrepFenceError,
  ExportPrepRepository,
  isValidStagedSha256,
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
  stagingFileExists,
  deleteSessionExportStaging,
} from './exportStaging';
import type { ExportPrepCounts, ExportPrepJobRow, EnsureExportPrepJobsResult, ExportPrepEnsureReason } from './exportPrepTypes';
import { emptyExportPrepCounts, emptyEnsureExportPrepJobsResult } from './exportPrepTypes';
import { hashStagedFileSha256Hex } from './stagedSha256';
import {
  listCanonicalExportPhotos,
  selectEligibleExportPrepPhotos,
  selectNonProcessableExportPhotos,
  selectExportPackagingPhotos,
} from './eligibleExportPhotos';

export type { ExportPrepCounts, EnsureExportPrepJobsResult, ExportPrepEnsureReason } from './exportPrepTypes';
export { emptyExportPrepCounts, emptyEnsureExportPrepJobsResult };

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

/**
 * Durable producer-consumer for local ZIP export preparation.
 * Does not block MediaStore capture; one worker by default.
 */
export class ExportPrepQueue {
  private workers = 0;
  private readonly maxWorkers: number;
  private readonly warningPendingThreshold: number;
  private readonly maxExportUncompressedBytes: number;
  private stopped = false;
  private readonly listeners = new Set<ExportPrepListener>();
  private preferredSessionId: string | null = null;
  private tickScheduled = false;
  private lastBackpressureWarnedAt = 0;
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
    }
    this.scheduleTick();
  }

  /**
   * Ensure one durable job per eligible stable photo (session or active freeze).
   * Idempotent; safe for historical sessions without prep rows.
   * Does not weaken lease fencing — never touches in-flight jobs with a valid lease.
   */
  async ensureJobsForEligiblePhotos(
    sessionId: string,
    options?: { readonly reason?: ExportPrepEnsureReason },
  ): Promise<EnsureExportPrepJobsResult> {
    const reason = options?.reason ?? 'RECOVERY';
    const started = Date.now();
    const base = emptyEnsureExportPrepJobsResult(sessionId, reason);
    const partialErrors: string[] = [];

    const { session, photos } = await listCanonicalExportPhotos(
      this.deps.captureRepo,
      sessionId,
    );
    if (!session) {
      this.deps.logger?.warn('export_prep', {
        code: 'EXPORT_PREP_BACKFILL_SESSION_MISSING',
        sessionId,
        reason,
      });
      return { ...base, durationMs: Date.now() - started, partialErrors: ['SESSION_MISSING'] };
    }

    const eligible = selectEligibleExportPrepPhotos(photos);
    const nonProcessable = selectNonProcessableExportPhotos(photos);
    let existingJobs = 0;
    let createdJobs = 0;
    let requeuedJobs = 0;
    let invalidatedReadyJobs = 0;
    let excludedJobs = 0;
    let missingSourcePhotos = 0;

    for (const photo of nonProcessable) {
      try {
        const existing = await this.deps.prepRepo.getByPhotoId(photo.id);
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

        const existing = await this.deps.prepRepo.getByPhotoId(photo.id);

        if (existing?.status === 'READY') {
          const readyOk = await this.isReadyJobComplete(existing);
          if (readyOk) {
            existingJobs += 1;
            continue;
          }
          await this.deps.prepRepo.invalidateReady(
            photo.id,
            'EXPORT_PREP_READY_INVALID',
            'READY inválido: staging/sha/size/nombre incompleto',
          );
          invalidatedReadyJobs += 1;
        } else if (existing?.status === 'FAILED_TERMINAL') {
          existingJobs += 1;
          continue;
        } else if (existing?.status === 'EXCLUDED') {
          // Eligible stable photo with EXCLUDED job — leave until explicit reinclude (Phase 4).
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
          // Expired lease: enqueueIdempotent requeues without resetting attempt_count.
        } else if (existing?.status === 'FAILED_RETRYABLE') {
          // Leave row; claimNext will pick up. Preserve attempt_count.
          existingJobs += 1;
          continue;
        } else if (existing?.status === 'QUEUED') {
          existingJobs += 1;
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
        const beforeStatus = existing?.status ?? null;
        const result = await this.deps.prepRepo.enqueueIdempotent({
          capturePhotoId: photo.id,
          captureSessionId: sessionId,
          sourceUri: photo.uri,
          sourceFingerprint: fingerprint,
          exportFileName,
        });
        if (result.created) {
          createdJobs += 1;
        } else if (beforeStatus != null) {
          requeuedJobs += 1;
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
    this.scheduleTick();

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
    });
    return result;
  }

  private async isReadyJobComplete(job: ExportPrepJobRow): Promise<boolean> {
    if (!job.staging_uri || !job.export_file_name) return false;
    if (!(job.size_bytes != null && job.size_bytes > 0)) return false;
    if (!isValidStagedSha256(job.sha256)) return false;
    return stagingFileExists(job.staging_uri);
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
   * Barrier: backfill jobs for eligible freeze/session photos, then wait until every
   * eligible photo is READY | EXCLUDED | FAILED_TERMINAL (no missing jobs / pending).
   */
  async waitUntilExportable(
    sessionId: string,
    options?: { readonly timeoutMs?: number; readonly pollMs?: number },
  ): Promise<ExportPrepSettleResult> {
    // Phase 3 drain barrier — kept available; Phase 2 finish path uses ensure only.
    await this.ensureJobsForEligiblePhotos(sessionId, { reason: 'RECOVERY' });
    const timeoutMs = options?.timeoutMs ?? 10 * 60_000;
    const pollMs = options?.pollMs ?? 250;
    const started = Date.now();
    this.preferredSessionId = sessionId;
    this.scheduleTick();
    let last = await this.evaluateExportability(sessionId);
    while (Date.now() - started < timeoutMs) {
      this.emit(sessionId, await this.deps.prepRepo.countsForSession(sessionId));
      if (last.pending === 0 && last.missingJobs === 0 && last.failedRetryable === 0) {
        return last;
      }
      await new Promise((r) => setTimeout(r, pollMs));
      this.scheduleTick();
      last = await this.evaluateExportability(sessionId);
    }
    return last;
  }

  /** @deprecated use waitUntilExportable — Phase 3 drain */
  async waitUntilSettled(
    sessionId: string,
    options?: { readonly timeoutMs?: number; readonly pollMs?: number },
  ): Promise<{ readonly ok: boolean; readonly unresolved: number } & ExportPrepSettleResult> {
    const result = await this.waitUntilExportable(sessionId, options);
    return {
      ...result,
      unresolved: result.pending + result.missingJobs + result.failedRetryable,
    };
  }

  async evaluateExportability(sessionId: string): Promise<ExportPrepSettleResult> {
    const { photos } = await listCanonicalExportPhotos(this.deps.captureRepo, sessionId);
    const eligible = selectExportPackagingPhotos(photos);
    const jobs = await this.deps.prepRepo.listForSession(sessionId);
    const byId = new Map(jobs.map((j) => [j.capture_photo_id, j]));
    let ready = 0;
    let excluded = 0;
    let failedTerminal = 0;
    let failedRetryable = 0;
    let pending = 0;
    let missingJobs = 0;
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
        case 'EXCLUDED':
          excluded += 1;
          break;
        case 'FAILED_TERMINAL':
          failedTerminal += 1;
          break;
        case 'FAILED_RETRYABLE':
          failedRetryable += 1;
          break;
        case 'QUEUED':
        case 'PREPARING':
        case 'SCANNING':
        case 'VALIDATING':
          pending += 1;
          break;
        default:
          pending += 1;
          break;
      }
    }
    for (const photo of photos.filter((p) => p.status === 'excluded')) {
      const job = byId.get(photo.id);
      if (job?.status === 'EXCLUDED') excluded += 1;
    }
    const accounted = ready + failedTerminal + failedRetryable + pending + missingJobs;
    const ok =
      missingJobs === 0 &&
      pending === 0 &&
      failedRetryable === 0 &&
      failedTerminal === 0 &&
      ready === eligible.length &&
      accounted === eligible.length;
    return {
      ok,
      totalEligible: eligible.length,
      ready,
      excluded,
      failed: failedTerminal + failedRetryable,
      pending,
      missingJobs,
      failedTerminal,
      failedRetryable,
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

  stop(): void {
    this.stopped = true;
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
      this.workers += 1;
      void this.processJob(job).finally(() => {
        this.workers -= 1;
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

      const staged = await stageOriginalPhotoVersioned({
        sessionId,
        sourceUri: photo.uri,
        exportFileName,
        previousStagingUri: job.staging_uri,
      });

      await this.deps.prepRepo.markScanning(job.capture_photo_id, leaseToken, {
        stagingUri: staged.stagingUri,
        exportFileName,
        sizeBytes: staged.sizeBytes,
        renewLeaseMs: 180_000,
      });

      await this.runCodeScanIfNeeded(photo, staged.stagingUri);

      await this.deps.prepRepo.markValidating(job.capture_photo_id, leaseToken, 60_000);

      const draftRow = await this.deps.draftRepo
        .listForSession(sessionId)
        .then((rows) => rows.find((d) => d.capture_photo_id === photo.id) ?? null)
        .catch(() => null);
      if (!isDraftExportReady(draftRow)) {
        throw Object.assign(new Error('EXPORT_PREP_DRAFT_NOT_READY'), {
          code: 'EXPORT_PREP_DRAFT_NOT_READY',
        });
      }

      let sha256: string;
      try {
        sha256 = await hashStagedFileSha256Hex(staged.stagingUri);
      } catch (error) {
        throw Object.assign(
          new Error(error instanceof Error ? error.message : 'EXPORT_PREP_HASH_FAILED'),
          { code: 'EXPORT_PREP_HASH_FAILED' },
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

  private async runCodeScanIfNeeded(
    photo: {
      readonly id: string;
      readonly capture_session_id: string;
      readonly client_file_id: string | null;
      readonly upload_cancel_requested?: number;
    },
    stagedUri: string,
  ): Promise<void> {
    const strategy = this.deps.localCodeScan;
    if (!strategy || !this.deps.localCodeScanEnabled) {
      return;
    }
    const existing = await this.deps.draftRepo
      .listForSession(photo.capture_session_id)
      .then((rows) => rows.find((d) => d.capture_photo_id === photo.id))
      .catch(() => undefined);
    if (isDraftExportReady(existing ?? null)) {
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
