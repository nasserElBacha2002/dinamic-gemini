import type { FeatureFlags } from '../../core/featureFlags';
import { mapProcessingPersistence, toProcessingState } from '../../core/processingState';
import { normalizePreparationProcessingMode } from '../../core/imagePreparationPolicy';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';
import type { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import {
  createMonotonicClock,
  emitObservability,
  networkAttributesFromConnectivity,
  normalizeObservabilityError,
  sessionMarkKey,
  type ObservabilityReporter,
  type TimingMarkStore,
} from '../../observability';
import { ApiError } from '../../services/api/apiClient';
import type { ApiClient } from '../../services/api/apiClient';
import type {
  AisleJobsResponseDto,
  AisleProcessingStateResponseDto,
  AisleStatusResponseDto,
  MergeResultsResponseDto,
  ProcessAisleResponseDto,
  RecoverAisleProcessingResponseDto,
} from '../../services/api/types';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import { createId } from '../../shared/createId';
import type { UploadQueue } from '../upload/uploadQueue';
import type { AisleAssetsApi } from '../upload/aisleAssetsApi';
import type { OrderedCaptureApi } from '../upload/orderedCaptureApi';
import type { ConfirmedLocalResultRepository } from '../../database/repositories/confirmedLocalResultRepository';
import { computeProcessingReadiness, type ProcessingReadiness } from './processingReadiness';
import {
  buildProcessAisleRequestBody,
  mapProcessStartErrorMessage,
  sanitizeIdentificationModeSelection,
  type AisleIdentificationMode,
} from './processingMode';
import { processingRunStore } from './processingRun';
import { validateCompleteSequence } from '../../core/captureSequenceValidation';
import { compactSequenceAssignments } from '../../core/captureSequence';
export type { ProcessingReadiness } from './processingReadiness';
export type { AisleIdentificationMode } from './processingMode';

/** @deprecated Prefer run-scoped keys via processingRunStore. Kept for tests of key shape. */
export function processIdempotencyKey(sessionId: string, runId?: string): string {
  if (runId) {
    return `mobile-process:${sessionId}:${runId}`;
  }
  return `mobile-process:${sessionId}`;
}

export type StartProcessOptions = {
  /** Explicit override. null/undefined → inherit (omit field). */
  readonly identificationMode?: AisleIdentificationMode | null;
};

export type ResultLoadState = 'loading' | 'complete' | 'partial' | 'pending' | 'error';

export interface ProcessingResultSummary {
  readonly inventoryId: string;
  readonly inventoryName: string;
  readonly aisleId: string;
  readonly aisleName: string;
  readonly loadState: ResultLoadState;
  readonly message: string | null;
  readonly processedPhotos: number;
  readonly positions: number | null;
  readonly pendingReview: number | null;
  readonly finishedAt: string | null;
  readonly jobId: string | null;
}

export interface ProcessingObservability {
  readonly reporter: ObservabilityReporter;
  readonly marks: TimingMarkStore;
  readonly connectivity?: ConnectivityService | null;
}

export interface ProcessingAuthoritativeGate {
  readonly flags: FeatureFlags;
  readonly confirmed: ConfirmedLocalResultRepository;
  /** Optional: skip position-label photos from product confirmation gate. */
  readonly drafts?: {
    listForPhoto(photoId: string): Promise<
      readonly {
        readonly status: string;
        readonly error_code: string | null;
      }[]
    >;
  };
}

export class ProcessingService {
  private processLocks = new Set<string>();
  private readonly clock = createMonotonicClock();

  constructor(
    private readonly api: ApiClient,
    private readonly repo: CaptureRepository,
    private readonly jobs: ProcessingJobRepository,
    private readonly uploadQueue: UploadQueue,
    private readonly assetsApi: AisleAssetsApi,
    private readonly logger: Logger,
    private readonly observability: ProcessingObservability | null = null,
    private readonly authoritativeGate: ProcessingAuthoritativeGate | null = null,
    private readonly orderedCapture: OrderedCaptureApi | null = null,
  ) {}

  async readiness(sessionId: string): Promise<ProcessingReadiness> {
    const photos = await this.repo.listPhotos(sessionId);
    const uploadGate = await this.uploadQueue.refreshSessionReadiness(sessionId);
    const base = computeProcessingReadiness(photos, uploadGate);
    if (!base.ready) {
      return base;
    }
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      return { ...base, ready: false, reason: 'Sesión no encontrada.' };
    }
    const remoteDeletePending = photos.some((p) => p.upload_status === 'remote_delete_pending');
    if (remoteDeletePending) {
      return { ...base, ready: false, reason: 'Hay eliminaciones remotas pendientes.' };
    }
    try {
      const remote = await this.assetsApi.listAssets(session.inventory_id, session.aisle_id);
      const remoteIds = new Set(remote.map((a) => a.id));
      const valid = photos.filter(
        (p) => p.status === 'stable' && p.upload_status === 'uploaded' && p.backend_asset_id,
      );
      const missing = valid.filter((p) => p.backend_asset_id && !remoteIds.has(p.backend_asset_id));
      if (missing.length > 0) {
        return {
          ...base,
          ready: false,
          reason: `Faltan ${missing.length} asset(s) en el backend. Reintentá la reconciliación.`,
        };
      }
    } catch (e) {
      return { ...base, ready: false, reason: `No se pudo validar assets remotos: ${String(e)}` };
    }
    const authoritative = await this.checkAuthoritativeLocalResults(sessionId, photos);
    if (!authoritative.ready) {
      return { ...base, ready: false, reason: authoritative.reason };
    }
    return base;
  }

  private async checkAuthoritativeLocalResults(
    sessionId: string,
    photos: readonly CapturePhotoRow[],
  ): Promise<{ ready: boolean; reason: string | null }> {
    const gate = this.authoritativeGate;
    if (!gate?.flags.mobileAuthoritativeLocalCodeScan) {
      return { ready: true, reason: null };
    }
    // Fail-closed: when local authority is on, do not start remote /process until every
    // uploaded photo is confirmed+SYNCED or explicitly excluded.
    const uploaded = photos.filter(
      (p) => p.upload_status === 'uploaded' && Boolean(p.backend_asset_id),
    );
    const confirmed = await gate.confirmed.listForSession(sessionId);
    const byPhoto = new Map(confirmed.map((c) => [c.capture_photo_id, c]));
    const missing: string[] = [];
    for (const photo of uploaded) {
      if (gate.drafts) {
        const drafts = await gate.drafts.listForPhoto(photo.id);
        if (drafts.some((d) => d.error_code === 'POSITION_LABEL_DETECTED')) {
          // Position labels are resolved server-side; no product confirmation required.
          continue;
        }
      }
      const row = byPhoto.get(photo.id);
      if (!row || row.sync_status !== 'SYNCED') {
        missing.push(photo.display_name || photo.id);
      }
    }
    if (missing.length > 0) {
      return {
        ready: false,
        reason: `Faltan resultados locales confirmados/sincronizados (${missing.length}). No se inicia procesamiento remoto.`,
      };
    }
    return { ready: true, reason: null };
  }

  /**
   * Seal the backend ordered-capture session before POST /process.
   * No-op when no ordered session was created for this capture.
   *
   * Preflights against remote assets so we can rebind orphans (uploaded without
   * ordered_capture_session_id) instead of failing with a generic seal error.
   */
  private async sealOrderedCaptureBeforeProcess(
    session: CaptureSessionRow,
  ): Promise<{ ok: boolean; reason: string | null }> {
    const orderedId = session.backend_ordered_capture_session_id;
    if (!orderedId || !this.orderedCapture) {
      return { ok: true, reason: null };
    }
    const photos = await this.repo.listPhotos(session.id);
    const localUploaded = photos.filter(
      (p) => p.upload_status === 'uploaded' && p.sequence_number != null && p.backend_asset_id,
    );
    if (localUploaded.length < 1) {
      return {
        ok: false,
        reason: 'No hay fotos subidas con secuencia para sellar la sesión ordenada.',
      };
    }

    // After exclusions, sequences may have gaps (e.g. 1,2,3,5,6). Compact to 1..N
    // and rebind so the backend seal validator accepts the set.
    await this.repo.clearSequenceNumbersForExcluded(session.id);
    const compaction = compactSequenceAssignments(localUploaded);
    if (compaction.length > 0) {
      await this.repo.applySequenceCompaction(compaction);
      const rebound = await this.uploadQueue.rebindOrderedCaptureUploads(
        session.id,
        compaction.map((c) => c.id),
      );
      return {
        ok: false,
        reason:
          rebound.requeued > 0
            ? `Se reordenó la secuencia tras exclusiones (${rebound.requeued} foto(s)). ` +
              'Esperá a que terminen de resubir e intentá Procesar de nuevo.'
            : 'Se reordenó la secuencia local; reintentá Procesar.',
      };
    }

    const expectedAssetCount = localUploaded.length;
    const localAssetIds = new Set(localUploaded.map((p) => p.backend_asset_id as string));

    try {
      const remote = await this.assetsApi.listAssets(session.inventory_id, session.aisle_id);
      const sessionAssetsAll = remote.filter(
        (a) => (a.ordered_capture_session_id || '') === orderedId,
      );
      // Leftover remote assets from excluded photos break seal (max seq > count).
      const orphans = sessionAssetsAll.filter((a) => !localAssetIds.has(a.id));
      for (const orphan of orphans) {
        try {
          await this.assetsApi.deleteAsset(session.inventory_id, session.aisle_id, orphan.id);
        } catch (e) {
          this.logger.warn('ordered_capture_orphan_delete_failed', {
            sessionId: session.id,
            assetId: orphan.id,
            error: String(e),
          });
        }
      }
      const sessionAssets = sessionAssetsAll.filter((a) => localAssetIds.has(a.id));
      const remoteReasons = validateCompleteSequence(sessionAssets, expectedAssetCount, {
        requireClientImageId: false,
      });
      if (remoteReasons.length > 0) {
        const orphanPhotoIds = localUploaded
          .filter((p) => {
            const asset = remote.find((a) => a.id === p.backend_asset_id);
            return (
              !asset ||
              (asset.ordered_capture_session_id || '') !== orderedId ||
              asset.sequence_number !== p.sequence_number
            );
          })
          .map((p) => p.id);
        if (orphanPhotoIds.length > 0) {
          const rebound = await this.uploadQueue.rebindOrderedCaptureUploads(
            session.id,
            orphanPhotoIds,
          );
          if (rebound.ok && rebound.requeued > 0) {
            return {
              ok: false,
              reason:
                `Algunas fotos no quedaron vinculadas a la secuencia ordenada (${rebound.requeued}). ` +
                'Se reencolaron para resubir; esperá a que terminen e intentá Procesar de nuevo.',
            };
          }
        }
        return {
          ok: false,
          reason: `No se pudo sellar la sesión ordenada: ${remoteReasons.join('; ')}`,
        };
      }
    } catch (e) {
      this.logger.warn('ordered_capture_seal_preflight_failed', {
        sessionId: session.id,
        error: String(e),
      });
      // Fall through to seal; server remains authoritative.
    }

    try {
      await this.orderedCapture.sealSession(orderedId, {
        expected_asset_count: expectedAssetCount,
        sequence_version: 1,
      });
      return { ok: true, reason: null };
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'STRATEGY_DISABLED' || e.status === 422)) {
        // Already sealed or feature disabled — continue to process when safe.
        const detail = (e.message || '').toLowerCase();
        if (e.code === 'STRATEGY_DISABLED') {
          return { ok: true, reason: null };
        }
        if (detail.includes('already') || detail.includes('sealed')) {
          return { ok: true, reason: null };
        }
      }
      return {
        ok: false,
        reason:
          e instanceof ApiError
            ? `No se pudo sellar la sesión ordenada: ${e.message}`
            : `No se pudo sellar la sesión ordenada: ${String(e)}`,
      };
    }
  }

  async validateBeforeProcess(sessionId: string): Promise<{ ok: boolean; reason: string | null }> {
    const readiness = await this.readiness(sessionId);
    return { ok: readiness.ready, reason: readiness.reason };
  }

  async startProcess(
    sessionId: string,
    options: StartProcessOptions = {},
  ): Promise<{ ok: boolean; jobId: string | null; reason: string | null }> {
    if (this.processLocks.has(sessionId)) {
      return { ok: false, jobId: null, reason: 'Procesamiento ya en curso.' };
    }
    this.processLocks.add(sessionId);
    const identificationMode = sanitizeIdentificationModeSelection(options.identificationMode);
    const run = await processingRunStore.getOrCreateForStart(sessionId, identificationMode);
    const idempotencyKey = run.idempotencyKey;
    try {
      const check = await this.validateBeforeProcess(sessionId);
      if (!check.ok) {
        await processingRunStore.markTerminal(run.id, 'failed');
        return { ok: false, jobId: null, reason: check.reason };
      }
      const session = await this.repo.getSession(sessionId);
      if (!session) {
        await processingRunStore.markTerminal(run.id, 'failed');
        return { ok: false, jobId: null, reason: 'Sesión no encontrada.' };
      }

      if (identificationMode) {
        await this.repo.setPreparationProcessingMode(
          sessionId,
          normalizePreparationProcessingMode(identificationMode),
        );
      }

      if (run.backendJobId) {
        const existing = await this.jobs.getByBackendJobId(run.backendJobId);
        if (existing && (existing.status === 'pending' || existing.status === 'running' || existing.status === 'unknown')) {
          return { ok: true, jobId: run.backendJobId, reason: null };
        }
      }

      if (session.backend_job_id) {
        const existing = await this.jobs.getByBackendJobId(session.backend_job_id);
        if (existing && (existing.status === 'pending' || existing.status === 'running' || existing.status === 'unknown')) {
          await processingRunStore.attachBackendJob(run.id, session.backend_job_id);
          return { ok: true, jobId: session.backend_job_id, reason: null };
        }
      }

      const recoveredRemote = await this.findActiveRemoteJob(session.inventory_id, session.aisle_id, idempotencyKey);
      if (recoveredRemote) {
        await processingRunStore.attachBackendJob(run.id, recoveredRemote.id);
        await this.repo.confirmProcessAttempt(sessionId, recoveredRemote.id);
        await this.persistJob(
          sessionId,
          session.inventory_id,
          session.aisle_id,
          recoveredRemote.id,
          recoveredRemote.status,
        );
        return { ok: true, jobId: recoveredRemote.id, reason: null };
      }

      // Preflight (compact / rebind / seal) must complete before durable STARTING.
      // Otherwise a recoverable seal failure leaves the session stuck "Iniciando".
      const sealed = await this.sealOrderedCaptureBeforeProcess(session);
      if (!sealed.ok) {
        const needsReupload = /reencolar|resubir|reordenó/i.test(sealed.reason ?? '');
        await this.repo.markProcessStartFailed(sessionId, {
          errorCode: 'PROCESS_PREFLIGHT_FAILED',
          message: sealed.reason ?? 'No se pudo completar la preparación previa al procesamiento.',
          sessionStatus: needsReupload ? 'uploading' : 'ready_to_process',
          clearBackendJobId: true,
        });
        await processingRunStore.markTerminal(run.id, 'failed');
        return { ok: false, jobId: null, reason: sealed.reason };
      }

      await this.repo.updateSessionUploadMeta(sessionId, {
        processingStatus: 'starting',
        processingStartedAt: new Date().toISOString(),
        lastProcessingError: null,
      });
      try {
        await this.repo.updateSessionStatus(sessionId, 'processing');
      } catch {
        // already processing
      }

      const processAttemptId = createId();
      const processRequestedAt = new Date().toISOString();
      await this.repo.persistProcessAttempt(sessionId, {
        processAttemptId,
        processIdempotencyKey: idempotencyKey,
        processRequestedAt,
      });

      const path =
        `/api/v3/inventories/${encodeURIComponent(session.inventory_id)}` +
        `/aisles/${encodeURIComponent(session.aisle_id)}/process`;
      const body = buildProcessAisleRequestBody(idempotencyKey, identificationMode);
      const uploadsCompletedToProcessMs =
        this.observability?.marks.takeElapsedMs(sessionMarkKey(sessionId, 'all_uploads_completed')) ?? null;
      const processStartedAt = this.clock.nowMs();
      emitObservability(this.observability?.reporter, {
        name: 'session.process_requested',
        sessionId,
        attemptId: processAttemptId,
        attributes: {
          all_uploads_completed_to_process_requested_ms: uploadsCompletedToProcessMs,
          identification_mode: identificationMode ?? 'inherited',
          ...networkAttributesFromConnectivity(this.observability?.connectivity),
        },
      });
      try {
        const response = await this.api.post<ProcessAisleResponseDto>(path, body, {
          headers: { 'Idempotency-Key': idempotencyKey },
        });
        const processRequestMs = Math.max(0, Math.round(this.clock.nowMs() - processStartedAt));
        await processingRunStore.attachBackendJob(run.id, response.job_id);
        await this.repo.confirmProcessAttempt(sessionId, response.job_id);
        await this.persistJob(sessionId, session.inventory_id, session.aisle_id, response.job_id, 'queued');
        this.observability?.marks.mark(sessionMarkKey(sessionId, 'process_requested'));
        this.observability?.marks.mark(sessionMarkKey(sessionId, `job:${response.job_id}:queued`));
        emitObservability(this.observability?.reporter, {
          name: 'session.process_accepted',
          sessionId,
          serverJobId: response.job_id,
          attemptId: processAttemptId,
          durationMs: processRequestMs,
          attributes: {
            process_request_ms: processRequestMs,
            execution_strategy: response.execution_strategy ?? null,
            ...networkAttributesFromConnectivity(this.observability?.connectivity),
          },
        });
        this.logger.info('job_started', {
          sessionId,
          jobId: response.job_id,
          runId: run.id,
          idempotencyKey,
          identificationMode: identificationMode ?? 'inherited',
          executionStrategy: response.execution_strategy ?? null,
        });
        return { ok: true, jobId: response.job_id, reason: null };
      } catch (e) {
        const processRequestMs = Math.max(0, Math.round(this.clock.nowMs() - processStartedAt));
        emitObservability(this.observability?.reporter, {
          name: 'session.process_failed',
          sessionId,
          attemptId: processAttemptId,
          durationMs: processRequestMs,
          attributes: {
            process_request_ms: processRequestMs,
            error_code: normalizeObservabilityError({
              stage: 'process',
              code: e instanceof ApiError ? e.code : null,
              httpStatus: e instanceof ApiError ? e.status : null,
              message: e instanceof ApiError ? e.message : String(e),
            }),
          },
        });
        if (e instanceof ApiError && (e.status === 409 || e.code === 'ACTIVE_JOB_EXISTS')) {
          const recovered = await this.findActiveRemoteJob(session.inventory_id, session.aisle_id, idempotencyKey);
          if (recovered) {
            await processingRunStore.attachBackendJob(run.id, recovered.id);
            await this.repo.confirmProcessAttempt(sessionId, recovered.id);
            await this.persistJob(sessionId, session.inventory_id, session.aisle_id, recovered.id, recovered.status);
            return { ok: true, jobId: recovered.id, reason: null };
          }
        }
        if (e instanceof ApiError && (e.code === 'NETWORK_ERROR' || e.status === null)) {
          const recovered = await this.findActiveRemoteJob(session.inventory_id, session.aisle_id, idempotencyKey);
          if (recovered) {
            await processingRunStore.attachBackendJob(run.id, recovered.id);
            await this.repo.confirmProcessAttempt(sessionId, recovered.id);
            await this.persistJob(sessionId, session.inventory_id, session.aisle_id, recovered.id, recovered.status);
            return { ok: true, jobId: recovered.id, reason: null };
          }
          // Keep run active so a manual retry reuses the same idempotency key.
          // Do not leave durable STARTING without a confirmed job_id.
          await this.repo.markProcessStartFailed(sessionId, {
            errorCode: 'PROCESS_RESPONSE_LOST',
            message:
              'No se pudo confirmar el inicio del procesamiento. Verificá la conexión e intentá nuevamente.',
            sessionStatus: 'uploading',
            clearBackendJobId: true,
          });
          return {
            ok: false,
            jobId: null,
            reason:
              'No se pudo iniciar el procesamiento. Verificá tu conexión e intentá nuevamente. ' +
              'No reintentamos automáticamente para evitar jobs duplicados.',
          };
        }
        if (e instanceof ApiError) {
          await this.repo.markProcessStartFailed(sessionId, {
            errorCode: e.code ?? `HTTP_${e.status ?? 'ERROR'}`,
            message: mapProcessStartErrorMessage(e),
            sessionStatus: 'uploading',
            clearBackendJobId: true,
          });
          await processingRunStore.markTerminal(run.id, 'failed');
          return {
            ok: false,
            jobId: null,
            reason: mapProcessStartErrorMessage(e),
          };
        }
        await this.repo.markProcessStartFailed(sessionId, {
          errorCode: 'PROCESS_START_FAILED',
          message: String(e),
          sessionStatus: 'uploading',
          clearBackendJobId: true,
        });
        await processingRunStore.markTerminal(run.id, 'failed');
        return {
          ok: false,
          jobId: null,
          reason: String(e),
        };
      }
    } finally {
      this.processLocks.delete(sessionId);
    }
  }

  async getSessionProcessingView(sessionId: string): Promise<{
    state: ReturnType<typeof toProcessingState>;
    localState: ReturnType<typeof toProcessingState>;
    remoteStatus: string | null;
    jobId: string | null;
    inventoryId: string | null;
    aisleId: string | null;
    errorMessage: string | null;
    finishedAt: string | null;
    updatedAt: string | null;
  }> {
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      return {
        state: 'idle',
        localState: 'idle',
        remoteStatus: null,
        jobId: null,
        inventoryId: null,
        aisleId: null,
        errorMessage: null,
        finishedAt: null,
        updatedAt: null,
      };
    }
    const latest = await this.jobs.getLatestForSession(sessionId);
    const remoteStatus = latest?.remote_status ?? session.processing_status ?? null;
    const state = toProcessingState(remoteStatus);
    return {
      state,
      localState: toProcessingState(session.processing_status),
      remoteStatus,
      jobId: latest?.backend_job_id ?? session.backend_job_id,
      inventoryId: session.inventory_id,
      aisleId: session.aisle_id,
      errorMessage: latest?.error_message ?? session.last_processing_error,
      finishedAt: latest?.finished_at ?? session.processing_finished_at,
      updatedAt: latest?.last_polled_at ?? session.updated_at,
    };
  }

  async getResultSummary(sessionId: string): Promise<ProcessingResultSummary> {
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      return {
        inventoryId: '',
        inventoryName: '',
        aisleId: '',
        aisleName: '',
        loadState: 'error',
        message: 'Sesión no encontrada.',
        processedPhotos: 0,
        positions: null,
        pendingReview: null,
        finishedAt: null,
        jobId: null,
      };
    }
    const photos = await this.repo.listPhotos(sessionId);
    const processedPhotos = photos.filter((p) => p.upload_status === 'uploaded').length;
    const view = await this.getSessionProcessingView(sessionId);
    const base = {
      inventoryId: session.inventory_id,
      inventoryName: session.inventory_name,
      aisleId: session.aisle_id,
      aisleName: session.aisle_name,
      processedPhotos,
      finishedAt: view.finishedAt,
      jobId: view.jobId,
    };

    if (view.state !== 'completed') {
      return {
        ...base,
        loadState: view.state === 'failed' || view.state === 'cancelled' ? 'error' : 'pending',
        message:
          view.state === 'failed'
            ? view.errorMessage ?? 'El procesamiento falló.'
            : 'El resultado todavía no está disponible.',
        positions: null,
        pendingReview: null,
      };
    }

    try {
      const merge = await this.getMergeResults(session.inventory_id, session.aisle_id, view.jobId);
      if (merge.results.length > 0) {
        return {
          ...base,
          loadState: 'complete',
          message: 'Resultado completo',
          positions: merge.results.length,
          pendingReview: merge.results.filter((r) => r.review_required).length,
        };
      }
      try {
        const status = await this.getAisleStatus(session.inventory_id, session.aisle_id);
        return {
          ...base,
          loadState: 'partial',
          message: 'Resultado parcial (merge vacío; usando métricas del pasillo)',
          positions: status.aisle.positions_count ?? 0,
          pendingReview: status.aisle.pending_review_positions_count ?? 0,
        };
      } catch {
        return {
          ...base,
          loadState: 'pending',
          message: 'Resultado todavía no disponible (consolidación pendiente)',
          positions: null,
          pendingReview: null,
        };
      }
    } catch (e) {
      const message =
        e instanceof ApiError && e.status === 403
          ? 'No tenés permisos para consultar el resultado.'
          : e instanceof ApiError
            ? e.message
            : `No se pudo consultar el resultado: ${String(e)}`;
      return {
        ...base,
        loadState: 'error',
        message,
        positions: null,
        pendingReview: null,
      };
    }
  }

  async getMergeResults(
    inventoryId: string,
    aisleId: string,
    jobId?: string | null,
  ): Promise<MergeResultsResponseDto> {
    const params = jobId?.trim() ? `?job_id=${encodeURIComponent(jobId.trim())}` : '';
    return this.api.get<MergeResultsResponseDto>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/merge-results${params}`,
    );
  }

  async getAisleStatus(inventoryId: string, aisleId: string): Promise<AisleStatusResponseDto> {
    return this.api.get<AisleStatusResponseDto>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/status`,
    );
  }

  async getAisleProcessingState(
    inventoryId: string,
    aisleId: string,
  ): Promise<AisleProcessingStateResponseDto> {
    return this.api.get<AisleProcessingStateResponseDto>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/processing-state`,
    );
  }

  async recoverAisleProcessing(
    inventoryId: string,
    aisleId: string,
    body: { readonly reason?: string; readonly dry_run?: boolean } = {},
  ): Promise<RecoverAisleProcessingResponseDto> {
    return this.api.post<RecoverAisleProcessingResponseDto>(
      `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/processing/recover`,
      { reason: body.reason ?? 'mobile_stuck_starting', dry_run: body.dry_run ?? false },
    );
  }

  async applyRemoteStatus(
    sessionId: string,
    inventoryId: string,
    aisleId: string,
    backendJobId: string,
    remoteStatus: string,
    errorMessage?: string | null,
  ): Promise<void> {
    await this.persistJob(sessionId, inventoryId, aisleId, backendJobId, remoteStatus, errorMessage);
  }

  /**
   * Bootstrap recovery: sessions left in durable STARTING without a confirmed backend job
   * (crash / seal failure / lost response) must not block reprocess forever.
   */
  async recoverStuckStartingSessions(options?: {
    readonly ttlMs?: number;
  }): Promise<{ recovered: number }> {
    const ttlMs = options?.ttlMs ?? 2 * 60 * 1000;
    const cutoff = new Date(Date.now() - ttlMs).toISOString();
    const stuck = await this.repo.listSessionsStuckStarting(cutoff);
    let recovered = 0;
    for (const session of stuck) {
      try {
        await this.repo.touchRecoveryCheck(session.id);
        const idempotencyKey = session.process_idempotency_key?.trim() ?? '';

        let processingState: AisleProcessingStateResponseDto | null = null;
        try {
          processingState = await this.getAisleProcessingState(session.inventory_id, session.aisle_id);
        } catch (e) {
          this.logger.warn('recovery', {
            sessionId: session.id,
            error: String(e),
            reason: 'processing_state_unavailable',
          });
        }

        if (processingState?.recoverable && processingState.job_id) {
          try {
            const recoverResult = await this.recoverAisleProcessing(
              session.inventory_id,
              session.aisle_id,
              { reason: 'mobile_stuck_starting' },
            );
            processingState = recoverResult.processing_state;
          } catch (e) {
            this.logger.warn('recovery', {
              sessionId: session.id,
              error: String(e),
              reason: 'processing_recover_failed',
            });
          }
        }

        const activeRemote = this.extractActiveRemoteFromState(processingState);
        if (activeRemote && idempotencyKey) {
          if (processingState?.idempotency_key === idempotencyKey) {
            await this.persistJob(
              session.id,
              session.inventory_id,
              session.aisle_id,
              activeRemote.id,
              activeRemote.status,
            );
            await this.repo.confirmProcessAttempt(session.id, activeRemote.id);
            recovered += 1;
            continue;
          }
          await this.repo.markProcessStartFailed(session.id, {
            errorCode: 'REMOTE_JOB_EXISTS_NOT_OWNED',
            message:
              'Hay un procesamiento activo en el servidor que no corresponde a este intento local. ' +
              'Revisá el pasillo antes de volver a procesar.',
            sessionStatus: 'ready_to_process',
            clearBackendJobId: true,
          });
          recovered += 1;
          continue;
        }

        if (idempotencyKey) {
          const remote = await this.findActiveRemoteJob(
            session.inventory_id,
            session.aisle_id,
            idempotencyKey,
          );
          if (remote) {
            await this.persistJob(
              session.id,
              session.inventory_id,
              session.aisle_id,
              remote.id,
              remote.status,
            );
            await this.repo.confirmProcessAttempt(session.id, remote.id);
            recovered += 1;
            continue;
          }
        }

        if (activeRemote && !idempotencyKey) {
          await this.repo.markProcessStartFailed(session.id, {
            errorCode: 'REMOTE_JOB_EXISTS_NOT_OWNED',
            message:
              'Hay un procesamiento activo en el servidor sin identidad local confirmada. ' +
              'No se adoptó el job remoto automáticamente.',
            sessionStatus: 'ready_to_process',
            clearBackendJobId: true,
          });
          recovered += 1;
          continue;
        }

        await this.repo.markProcessStartFailed(session.id, {
          errorCode: 'STUCK_STARTING_TTL',
          message:
            'El inicio local quedó incompleto sin job confirmado. Podés volver a procesar.',
          sessionStatus: 'ready_to_process',
          clearBackendJobId: true,
        });
        recovered += 1;
      } catch (e) {
        this.logger.warn('recovery', {
          sessionId: session.id,
          error: String(e),
          reason: 'stuck_starting_recovery_failed',
        });
      }
    }
    return { recovered };
  }

  private extractActiveRemoteFromState(
    state: AisleProcessingStateResponseDto | null,
  ): { id: string; status: string } | null {
    if (!state?.job_id?.trim()) {
      return null;
    }
    const status = (state.job_status ?? state.state ?? 'queued').toLowerCase();
    if (!['queued', 'starting', 'running', 'cancel_requested'].includes(status)) {
      return null;
    }
    return { id: state.job_id, status: state.job_status ?? state.state };
  }

  private async findActiveRemoteJob(
    inventoryId: string,
    aisleId: string,
    idempotencyKey: string,
  ): Promise<{ id: string; status: string } | null> {
    const key = idempotencyKey.trim();
    if (!key) {
      return null;
    }
    try {
      const state = await this.getAisleProcessingState(inventoryId, aisleId);
      if (state.job_id && state.idempotency_key === key) {
        return { id: state.job_id, status: state.job_status ?? state.state ?? 'queued' };
      }

      const jobs = await this.api.get<AisleJobsResponseDto>(
        `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/jobs?limit=20`,
      );
      const byKey = jobs.jobs.find((j) => {
        const payload = (j as { payload_json?: { idempotency_key?: string } }).payload_json;
        return payload?.idempotency_key === key;
      });
      if (byKey) {
        return { id: byKey.id, status: byKey.status };
      }
      return null;
    } catch {
      return null;
    }
  }

  private async persistJob(
    sessionId: string,
    inventoryId: string,
    aisleId: string,
    backendJobId: string,
    remoteStatus: string,
    errorMessage?: string | null,
  ): Promise<void> {
    const mapping = mapProcessingPersistence(remoteStatus);
    const existing = await this.jobs.getByBackendJobId(backendJobId);
    if (!existing) {
      await this.jobs.create({
        captureSessionId: sessionId,
        inventoryId,
        aisleId,
        backendJobId,
        status: mapping.jobStatus,
        remoteStatus,
      });
    } else {
      await this.jobs.updatePoll({
        id: existing.id,
        status: mapping.jobStatus,
        remoteStatus,
        nextPollAt: mapping.terminal ? null : new Date(Date.now() + 4000).toISOString(),
        errorMessage: errorMessage ?? null,
        finished: mapping.terminal,
      });
    }

    await this.repo.updateSessionUploadMeta(sessionId, {
      processingStatus: remoteStatus,
      backendJobId,
      processingStartedAt: new Date().toISOString(),
      lastProcessingError: mapping.terminal && mapping.state !== 'completed' ? errorMessage ?? remoteStatus : null,
      processingFinishedAt: mapping.terminal ? new Date().toISOString() : null,
    });

    try {
      await this.repo.updateSessionStatus(sessionId, mapping.captureStatus, mapping.terminal && mapping.state === 'completed');
    } catch {
      // transition may already be applied
    }
  }
}
