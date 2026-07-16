import { mapRemoteJobStatus } from '../../core/captureState';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import type { ProcessingJobRow } from '../../database/schema/captureSchema';
import type { ApiClient } from '../../services/api/apiClient';
import type { AisleStatusResponseDto } from '../../services/api/types';

export interface JobMonitorSnapshot {
  readonly jobs: readonly ProcessingJobRow[];
}

export type JobListener = (snapshot: JobMonitorSnapshot) => void;

export class JobMonitor {
  private readonly timers = new Map<string, ReturnType<typeof setTimeout>>();
  private readonly listeners = new Set<JobListener>();
  private disposed = false;

  constructor(
    private readonly api: ApiClient,
    private readonly jobs: ProcessingJobRepository,
    private readonly sessions: CaptureRepository,
    private readonly logger: Logger,
  ) {}

  subscribe(listener: JobListener): () => void {
    this.listeners.add(listener);
    void this.emit();
    return () => this.listeners.delete(listener);
  }

  async restorePendingJobs(): Promise<void> {
    const pending = await this.jobs.listNonTerminal();
    for (const job of pending) {
      await this.watch(job.backend_job_id);
    }
  }

  async watch(backendJobId: string): Promise<void> {
    if (this.timers.has(backendJobId)) {
      return;
    }
    this.schedule(backendJobId, 0);
  }

  async refresh(backendJobId: string): Promise<void> {
    await this.pollOnce(backendJobId);
  }

  stop(backendJobId: string): void {
    const t = this.timers.get(backendJobId);
    if (t) {
      clearTimeout(t);
    }
    this.timers.delete(backendJobId);
  }

  dispose(): void {
    this.disposed = true;
    for (const id of [...this.timers.keys()]) {
      this.stop(id);
    }
    this.listeners.clear();
  }

  private schedule(backendJobId: string, delayMs: number): void {
    if (this.disposed) {
      return;
    }
    this.stop(backendJobId);
    const timer = setTimeout(() => {
      void this.pollOnce(backendJobId);
    }, delayMs);
    this.timers.set(backendJobId, timer);
  }

  private async pollOnce(backendJobId: string): Promise<void> {
    const job = await this.jobs.getByBackendJobId(backendJobId);
    if (!job) {
      this.stop(backendJobId);
      return;
    }
    try {
      const status = await this.api.get<AisleStatusResponseDto>(
        `/api/v3/inventories/${encodeURIComponent(job.inventory_id)}/aisles/${encodeURIComponent(job.aisle_id)}/status`,
      );
      const remote =
        status.latest_job?.id === backendJobId
          ? status.latest_job
          : status.recent_jobs.find((j) => j.id === backendJobId) ?? status.latest_job;
      const remoteStatus = remote?.status ?? 'unknown';
      const local = mapRemoteJobStatus(remoteStatus);
      const terminal = local === 'success' || local === 'failed' || local === 'cancelled';
      const nextDelay = terminal ? null : local === 'running' ? 4000 : 2500;
      await this.jobs.updatePoll({
        id: job.id,
        status: local === 'unknown' ? 'unknown' : local === 'pending' ? 'pending' : local === 'running' ? 'running' : local,
        remoteStatus,
        nextPollAt: nextDelay ? new Date(Date.now() + nextDelay).toISOString() : null,
        errorCode: remote?.failure_code ?? null,
        errorMessage: remote?.error_message ?? remote?.failure_message ?? null,
        finished: terminal,
      });
      this.logger.info('job_status_changed', { jobId: backendJobId, status: remoteStatus });
      if (terminal) {
        if (local === 'success') {
          try {
            await this.sessions.updateSessionStatus(job.capture_session_id, 'completed', true);
          } catch {
            // ignore
          }
          await this.sessions.updateSessionUploadMeta(job.capture_session_id, {
            processingStatus: remoteStatus,
            processingFinishedAt: new Date().toISOString(),
          });
        } else {
          try {
            await this.sessions.updateSessionStatus(job.capture_session_id, 'failed_processing');
          } catch {
            // ignore
          }
          await this.sessions.updateSessionUploadMeta(job.capture_session_id, {
            processingStatus: remoteStatus,
            lastProcessingError: remote?.error_message ?? remoteStatus,
            processingFinishedAt: new Date().toISOString(),
          });
        }
        this.stop(backendJobId);
      } else {
        this.schedule(backendJobId, nextDelay ?? 5000);
      }
      await this.emit();
    } catch (e) {
      this.logger.warn('job_poll_error', { jobId: backendJobId, message: String(e) });
      this.schedule(backendJobId, 10_000);
    }
  }

  private async emit(): Promise<void> {
    const jobs = await this.jobs.listNonTerminal();
    const snapshot = { jobs };
    for (const l of this.listeners) {
      l(snapshot);
    }
  }
}
