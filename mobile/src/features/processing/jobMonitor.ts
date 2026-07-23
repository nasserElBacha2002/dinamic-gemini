import { mapProcessingPersistence } from '../../core/processingState';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type { ProcessingJobRepository } from '../../database/repositories/processingJobRepository';
import type { ProcessingJobRow } from '../../database/schema/captureSchema';
import type { BackgroundWorkScheduler } from '../../native/backgroundWork';
import {
  emitObservability,
  normalizeObservabilityError,
  sessionMarkKey,
  type ObservabilityReporter,
  type TimingMarkStore,
} from '../../observability';
import type { ApiClient } from '../../services/api/apiClient';
import type { AisleStatusResponseDto } from '../../services/api/types';

export interface JobMonitorSnapshot {
  readonly jobs: readonly ProcessingJobRow[];
}

export type JobListener = (snapshot: JobMonitorSnapshot) => void;

export interface JobMonitorObservability {
  readonly reporter: ObservabilityReporter;
  readonly marks: TimingMarkStore;
}

export interface JobMonitorOptions {
  readonly backgroundPolling?: boolean;
  readonly backgroundWork?: BackgroundWorkScheduler | null;
  readonly observability?: JobMonitorObservability | null;
}

export class JobMonitor {
  private readonly timers = new Map<string, ReturnType<typeof setTimeout>>();
  private readonly listeners = new Set<JobListener>();
  private disposed = false;
  private readonly firstResultEmitted = new Set<string>();
  private readonly jobStartedEmitted = new Set<string>();

  constructor(
    private readonly api: ApiClient,
    private readonly jobs: ProcessingJobRepository,
    private readonly sessions: CaptureRepository,
    private readonly logger: Logger,
    private readonly options: JobMonitorOptions = {},
  ) {}

  subscribe(listener: JobListener): () => void {
    this.listeners.add(listener);
    void this.emit();
    return () => this.listeners.delete(listener);
  }

  async restorePendingJobs(): Promise<void> {
    const pending = await this.jobs.listNonTerminal();
    emitObservability(this.options.observability?.reporter, {
      name: 'job.monitor_restored',
      attributes: { pending_job_count: pending.length },
    });
    for (const job of pending) {
      await this.watch(job.backend_job_id);
    }
  }

  async watch(backendJobId: string): Promise<void> {
    if (this.timers.has(backendJobId)) {
      return;
    }
    if (this.options.backgroundPolling !== false && this.options.backgroundWork) {
      void this.options.backgroundWork.scheduleJobMonitor(backendJobId);
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
      if (this.options.backgroundWork) {
        void this.options.backgroundWork.cancelJobMonitor(id);
      }
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
    const obs = this.options.observability;
    try {
      const status = await this.api.get<AisleStatusResponseDto>(
        `/api/v3/inventories/${encodeURIComponent(job.inventory_id)}/aisles/${encodeURIComponent(job.aisle_id)}/status`,
      );
      const remote =
        status.latest_job?.id === backendJobId
          ? status.latest_job
          : status.recent_jobs.find((j) => j.id === backendJobId) ?? status.latest_job;
      const remoteStatus = remote?.status ?? 'unknown';
      const mapping = mapProcessingPersistence(remoteStatus);
      const nextDelay = mapping.terminal ? null : mapping.state === 'processing' ? 4000 : 2500;
      const errorMessage = remote?.error_message ?? remote?.failure_message ?? null;
      await this.jobs.updatePoll({
        id: job.id,
        status: mapping.jobStatus,
        remoteStatus,
        nextPollAt: nextDelay ? new Date(Date.now() + nextDelay).toISOString() : null,
        errorCode: remote?.failure_code ?? null,
        errorMessage,
        finished: mapping.terminal,
      });
      await this.sessions.updateSessionUploadMeta(job.capture_session_id, {
        processingStatus: remoteStatus,
        backendJobId,
        lastProcessingError: mapping.terminal && mapping.state !== 'completed' ? errorMessage : null,
        processingFinishedAt: mapping.terminal ? new Date().toISOString() : null,
      });
      try {
        await this.sessions.updateSessionStatus(
          job.capture_session_id,
          mapping.captureStatus,
          mapping.terminal && mapping.state === 'completed',
        );
      } catch {
        // ignore invalid transition races
      }
      this.logger.info('job_status_changed', { jobId: backendJobId, status: remoteStatus });

      const sessionId = job.capture_session_id;
      const statusLower = remoteStatus.toLowerCase();
      if (
        obs &&
        !this.jobStartedEmitted.has(backendJobId) &&
        (statusLower === 'running' || statusLower === 'starting' || mapping.state === 'processing')
      ) {
        this.jobStartedEmitted.add(backendJobId);
        const processToStart =
          obs.marks.takeElapsedMs(sessionMarkKey(sessionId, 'process_requested')) ?? null;
        obs.marks.mark(sessionMarkKey(sessionId, `job:${backendJobId}:started`));
        emitObservability(obs.reporter, {
          name: 'job.started_observed',
          sessionId,
          serverJobId: backendJobId,
          localJobId: job.id,
          durationMs: processToStart ?? undefined,
          attributes: {
            process_requested_to_job_started_ms: processToStart,
            remote_status: remoteStatus,
          },
        });
      }

      const positions = status.aisle.positions_count ?? 0;
      if (
        obs &&
        !this.firstResultEmitted.has(backendJobId) &&
        (positions > 0 || mapping.terminal)
      ) {
        this.firstResultEmitted.add(backendJobId);
        const startedKey = sessionMarkKey(sessionId, `job:${backendJobId}:started`);
        const jobToFirst =
          obs.marks.takeElapsedMs(startedKey) ??
          obs.marks.takeElapsedMs(sessionMarkKey(sessionId, 'process_requested'));
        const captureToFirst =
          obs.marks.takeElapsedMs(sessionMarkKey(sessionId, 'created')) ?? null;
        emitObservability(obs.reporter, {
          name: 'session.capture_to_first_server_result',
          sessionId,
          serverJobId: backendJobId,
          localJobId: job.id,
          durationMs: captureToFirst ?? undefined,
          attributes: {
            capture_to_first_server_result_ms: captureToFirst,
            job_started_to_first_result_ms: jobToFirst,
            positions_count: positions,
            remote_status: remoteStatus,
            approximated: positions === 0 && mapping.terminal,
          },
        });
      }

      if (mapping.terminal && obs) {
        const startedKey = sessionMarkKey(sessionId, `job:${backendJobId}:started`);
        const jobToTerminal =
          obs.marks.takeElapsedMs(startedKey) ??
          obs.marks.takeElapsedMs(sessionMarkKey(sessionId, 'process_requested'));
        const captureToTerminal =
          obs.marks.takeElapsedMs(sessionMarkKey(sessionId, 'created')) ?? null;
        const photos = await this.sessions.listPhotos(sessionId);
        const stable = photos.filter((p) => p.status === 'stable');
        emitObservability(obs.reporter, {
          name: 'session.job_terminal',
          sessionId,
          serverJobId: backendJobId,
          localJobId: job.id,
          durationMs: captureToTerminal ?? undefined,
          attributes: {
            capture_to_job_terminal_ms: captureToTerminal,
            capture_to_full_sync_ms: captureToTerminal,
            job_started_to_terminal_ms: jobToTerminal,
            remote_status: remoteStatus,
            total_images: stable.length,
            uploaded_images: stable.filter((p) => p.upload_status === 'uploaded').length,
            failed_images: stable.filter((p) =>
              ['permanent_error', 'retryable_error'].includes(p.upload_status),
            ).length,
            retryable_failures: stable.filter((p) => p.upload_status === 'retryable_error').length,
            terminal_failures: stable.filter((p) => p.upload_status === 'permanent_error').length,
            error_code:
              mapping.state === 'completed'
                ? null
                : normalizeObservabilityError({
                    stage: 'job',
                    code: remote?.failure_code ?? null,
                    message: errorMessage,
                  }),
          },
        });
        if (mapping.state !== 'completed') {
          emitObservability(obs.reporter, {
            name: 'job.terminal_failed',
            sessionId,
            serverJobId: backendJobId,
            attributes: {
              error_code: normalizeObservabilityError({
                stage: 'job',
                code: remote?.failure_code ?? null,
                message: errorMessage,
              }),
              remote_status: remoteStatus,
            },
          });
        }
      }

      if (mapping.terminal) {
        if (this.options.backgroundWork) {
          void this.options.backgroundWork.cancelJobMonitor(backendJobId);
        }
        this.stop(backendJobId);
      } else {
        this.schedule(backendJobId, nextDelay ?? 5000);
      }
      await this.emit();
    } catch (e) {
      this.logger.warn('job_poll_error', { jobId: backendJobId, message: String(e) });
      emitObservability(this.options.observability?.reporter, {
        name: 'job.poll_failed',
        sessionId: job.capture_session_id,
        serverJobId: backendJobId,
        attributes: {
          error_code: normalizeObservabilityError({
            stage: 'job',
            message: String(e),
          }),
        },
      });
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
