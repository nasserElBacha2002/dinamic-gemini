import { mapProcessingPersistence, toProcessingState } from '../../core/processingState';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
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
  AisleStatusResponseDto,
  MergeResultsResponseDto,
  ProcessAisleResponseDto,
} from '../../services/api/types';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import { createId } from '../../shared/createId';
import type { UploadQueue } from '../upload/uploadQueue';
import type { AisleAssetsApi } from '../upload/aisleAssetsApi';
import { computeProcessingReadiness, type ProcessingReadiness } from './processingReadiness';
import {
  buildProcessAisleRequestBody,
  mapProcessStartErrorMessage,
  sanitizeIdentificationModeSelection,
  type AisleIdentificationMode,
} from './processingMode';
import { processingRunStore } from './processingRun';

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
    return base;
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
        await this.persistJob(
          sessionId,
          session.inventory_id,
          session.aisle_id,
          recoveredRemote.id,
          recoveredRemote.status,
        );
        return { ok: true, jobId: recoveredRemote.id, reason: null };
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

      const path =
        `/api/v3/inventories/${encodeURIComponent(session.inventory_id)}` +
        `/aisles/${encodeURIComponent(session.aisle_id)}/process`;
      const body = buildProcessAisleRequestBody(idempotencyKey, identificationMode);
      const processAttemptId = createId();
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
            await this.persistJob(sessionId, session.inventory_id, session.aisle_id, recovered.id, recovered.status);
            return { ok: true, jobId: recovered.id, reason: null };
          }
        }
        if (e instanceof ApiError && (e.code === 'NETWORK_ERROR' || e.status === null)) {
          const recovered = await this.findActiveRemoteJob(session.inventory_id, session.aisle_id, idempotencyKey);
          if (recovered) {
            await processingRunStore.attachBackendJob(run.id, recovered.id);
            await this.persistJob(sessionId, session.inventory_id, session.aisle_id, recovered.id, recovered.status);
            return { ok: true, jobId: recovered.id, reason: null };
          }
          // Keep run active so a manual retry reuses the same idempotency key.
          return {
            ok: false,
            jobId: null,
            reason:
              'No se pudo iniciar el procesamiento. Verificá tu conexión e intentá nuevamente. ' +
              'No reintentamos automáticamente para evitar jobs duplicados.',
          };
        }
        if (e instanceof ApiError) {
          await processingRunStore.markTerminal(run.id, 'failed');
          return {
            ok: false,
            jobId: null,
            reason: mapProcessStartErrorMessage(e),
          };
        }
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

  private async findActiveRemoteJob(
    inventoryId: string,
    aisleId: string,
    idempotencyKey: string,
  ): Promise<{ id: string; status: string } | null> {
    try {
      const status = await this.api.get<AisleStatusResponseDto>(
        `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/status`,
      );
      const candidates = [
        status.latest_job,
        ...status.recent_jobs,
      ].filter(Boolean) as { id: string; status: string }[];
      const active = candidates.find((j) =>
        ['queued', 'starting', 'running', 'cancel_requested'].includes(j.status.toLowerCase()),
      );
      if (active) return active;
      const jobs = await this.api.get<AisleJobsResponseDto>(
        `/api/v3/inventories/${encodeURIComponent(inventoryId)}/aisles/${encodeURIComponent(aisleId)}/jobs?limit=20`,
      );
      const byKey = jobs.jobs.find((j) => {
        const payload = (j as { payload_json?: { idempotency_key?: string } }).payload_json;
        return payload?.idempotency_key === idempotencyKey;
      });
      if (byKey) return { id: byKey.id, status: byKey.status };
      const activeListed = jobs.jobs.find((j) =>
        ['queued', 'starting', 'running', 'cancel_requested'].includes(j.status.toLowerCase()),
      );
      return activeListed ? { id: activeListed.id, status: activeListed.status } : null;
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
