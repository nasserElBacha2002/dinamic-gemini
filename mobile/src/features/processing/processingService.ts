import { mapRemoteJobStatus } from '../../core/captureState';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import { ApiError } from '../../services/api/apiClient';
import type { ApiClient } from '../../services/api/apiClient';
import type {
  AisleJobsResponseDto,
  AisleStatusResponseDto,
  ProcessAisleResponseDto,
} from '../../services/api/types';
import type { UploadQueue } from '../upload/uploadQueue';
import type { AisleAssetsApi } from '../upload/aisleAssetsApi';

export class ProcessingService {
  private processLocks = new Set<string>();

  constructor(
    private readonly api: ApiClient,
    private readonly repo: CaptureRepository,
    private readonly jobs: ProcessingJobRepository,
    private readonly uploadQueue: UploadQueue,
    private readonly assetsApi: AisleAssetsApi,
    private readonly logger: Logger,
  ) {}

  async validateBeforeProcess(sessionId: string): Promise<{ ok: boolean; reason: string | null }> {
    const readiness = await this.uploadQueue.refreshSessionReadiness(sessionId);
    if (readiness === 'pending') {
      return { ok: false, reason: 'Aún hay cargas o validaciones pendientes.' };
    }
    if (readiness === 'blocked') {
      return { ok: false, reason: 'Hay errores permanentes de upload por resolver.' };
    }
    const session = await this.repo.getSession(sessionId);
    if (!session) {
      return { ok: false, reason: 'Sesión no encontrada.' };
    }
    const photos = await this.repo.listPhotos(sessionId);
    const valid = photos.filter(
      (p) => p.status === 'stable' && p.upload_status === 'uploaded' && p.backend_asset_id,
    );
    if (valid.length === 0) {
      return { ok: false, reason: 'No hay fotografías cargadas para procesar.' };
    }
    const remoteDeletePending = photos.some((p) => p.upload_status === 'remote_delete_pending');
    if (remoteDeletePending) {
      return { ok: false, reason: 'Hay eliminaciones remotas pendientes.' };
    }
    try {
      const remote = await this.assetsApi.listAssets(session.inventory_id, session.aisle_id);
      const remoteIds = new Set(remote.map((a) => a.id));
      const missing = valid.filter((p) => p.backend_asset_id && !remoteIds.has(p.backend_asset_id));
      if (missing.length > 0) {
        return {
          ok: false,
          reason: `Faltan ${missing.length} asset(s) en el backend. Reintentá la reconciliación.`,
        };
      }
    } catch (e) {
      return { ok: false, reason: `No se pudo validar assets remotos: ${String(e)}` };
    }
    return { ok: true, reason: null };
  }

  async startProcess(sessionId: string): Promise<{ ok: boolean; jobId: string | null; reason: string | null }> {
    if (this.processLocks.has(sessionId)) {
      return { ok: false, jobId: null, reason: 'Procesamiento ya en curso.' };
    }
    this.processLocks.add(sessionId);
    try {
      const check = await this.validateBeforeProcess(sessionId);
      if (!check.ok) {
        return { ok: false, jobId: null, reason: check.reason };
      }
      const session = await this.repo.getSession(sessionId);
      if (!session) {
        return { ok: false, jobId: null, reason: 'Sesión no encontrada.' };
      }
      if (session.backend_job_id) {
        const existing = await this.jobs.getByBackendJobId(session.backend_job_id);
        if (existing && (existing.status === 'pending' || existing.status === 'running')) {
          return { ok: true, jobId: session.backend_job_id, reason: null };
        }
      }
      const path =
        `/api/v3/inventories/${encodeURIComponent(session.inventory_id)}` +
        `/aisles/${encodeURIComponent(session.aisle_id)}/process`;
      try {
        const response = await this.api.post<ProcessAisleResponseDto>(path, {});
        await this.persistJob(sessionId, session.inventory_id, session.aisle_id, response.job_id, 'queued');
        this.logger.info('job_started', { sessionId, jobId: response.job_id });
        return { ok: true, jobId: response.job_id, reason: null };
      } catch (e) {
        if (e instanceof ApiError && e.status === 409 && e.code === 'ACTIVE_JOB_EXISTS') {
          const status = await this.api.get<AisleStatusResponseDto>(
            `/api/v3/inventories/${encodeURIComponent(session.inventory_id)}/aisles/${encodeURIComponent(session.aisle_id)}/status`,
          );
          const jobId = status.latest_job?.id ?? status.operational_job_id;
          if (jobId) {
            await this.persistJob(
              sessionId,
              session.inventory_id,
              session.aisle_id,
              jobId,
              status.latest_job?.status ?? 'running',
            );
            return { ok: true, jobId, reason: null };
          }
          const jobs = await this.api.get<AisleJobsResponseDto>(
            `/api/v3/inventories/${encodeURIComponent(session.inventory_id)}/aisles/${encodeURIComponent(session.aisle_id)}/jobs?limit=5`,
          );
          const active = jobs.jobs.find((j) =>
            ['queued', 'starting', 'running', 'cancel_requested'].includes(j.status),
          );
          if (active) {
            await this.persistJob(sessionId, session.inventory_id, session.aisle_id, active.id, active.status);
            return { ok: true, jobId: active.id, reason: null };
          }
        }
        return {
          ok: false,
          jobId: null,
          reason: e instanceof ApiError ? e.message : String(e),
        };
      }
    } finally {
      this.processLocks.delete(sessionId);
    }
  }

  private async persistJob(
    sessionId: string,
    inventoryId: string,
    aisleId: string,
    backendJobId: string,
    remoteStatus: string,
  ): Promise<void> {
    const local = mapRemoteJobStatus(remoteStatus);
    const existing = await this.jobs.getByBackendJobId(backendJobId);
    if (!existing) {
      await this.jobs.create({
        captureSessionId: sessionId,
        inventoryId,
        aisleId,
        backendJobId,
        status: local === 'success' || local === 'failed' || local === 'cancelled' ? local : 'pending',
        remoteStatus,
      });
    }
    await this.repo.updateSessionStatus(sessionId, 'processing');
    await this.repo.updateSessionUploadMeta(sessionId, {
      processingStatus: remoteStatus,
      backendJobId,
      processingStartedAt: new Date().toISOString(),
      lastProcessingError: null,
    });
  }
}
