import { computeRetryDelayMs } from '../../core/uploadBackoff';
import type { FeatureFlags } from '../../core/featureFlags';
import type { Logger } from '../../core/logging';
import { isSqliteMalformedError } from '../../database/sqliteErrors';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type {
  ConfirmedLocalResultRepository,
  ConfirmedLocalResultRow,
} from '../../database/repositories/confirmedLocalResultRepository';
import { emitObservability, type ObservabilityReporter } from '../../observability';
import { ApiError } from '../../services/api/apiClient';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import type { CaptureSessionRow } from '../../database/schema/captureSchema';
import type { AuthoritativeLocalResultApi } from './authoritativeLocalResultApi';
import { mapConfirmedToAuthoritativeRequest } from './authoritativeLocalResultPayloadMapper';
import {
  classifyAuthoritativeSyncError,
  type AuthoritativeSyncOutcome,
} from './authoritativeLocalResultSyncOutcomeClassifier';

/**
 * Authoritative sync: JS timer while app is open (same pattern as preliminary sync).
 * No separate WorkManager worker — avoids a second background stack. Limitation: sync
 * pauses when the process is killed until next app open / post-upload enqueue.
 */
export const AUTH_SYNC_LEASE_MS = 90_000;
export const AUTH_SYNC_REQUEST_TIMEOUT_MS = 30_000;
const SYNC_BATCH_MAX = 20;
const SYNC_CONCURRENCY = 2;
const SYNC_MAX_ATTEMPTS = 8;
const MAX_TIMER_DELAY_MS = 6 * 60 * 60_000;
/** Floor delay after a sync pass with attempts but zero progress (no synced/retry). */
export const AUTH_SYNC_NO_PROGRESS_MIN_DELAY_MS = 30_000;
const AUTH_SYNC_NO_PROGRESS_MAX_DELAY_MS = 15 * 60_000;

export interface AuthoritativeSyncSummary {
  attempted: number;
  synced: number;
  retry: number;
  rejected: number;
  conflict: number;
  failed_terminal: number;
  not_ready: number;
  endpoint_missing: number;
  skipped_lease: number;
}

export interface AuthoritativeLocalResultSyncServiceOptions {
  readonly flags: FeatureFlags;
  readonly confirmed: ConfirmedLocalResultRepository;
  readonly capture: CaptureRepository;
  readonly api: AuthoritativeLocalResultApi;
  readonly logger: Logger;
  readonly reporter?: ObservabilityReporter | null;
  readonly connectivity?: ConnectivityService | null;
  readonly nowMs?: () => number;
  readonly setTimeoutFn?: typeof setTimeout;
  readonly clearTimeoutFn?: typeof clearTimeout;
}

/**
 * Syncs operator-confirmed local CODE_SCAN results to the authoritative endpoint.
 * Never blocks upload completion; process gate may require SYNCED when flag is on.
 */
export class AuthoritativeLocalResultSyncService {
  private running = false;
  private featureUnavailableUntil = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private connectivityUnsub: (() => void) | null = null;
  private disposed = false;
  private noProgressBackoffMs = 0;
  private pausedForCorruptDb = false;

  constructor(private readonly options: AuthoritativeLocalResultSyncServiceOptions) {}

  startScheduler(): void {
    if (!this.isSyncEnabled() || this.disposed) {
      return;
    }
    void this.rescheduleRetryTimer();
    if (!this.connectivityUnsub && this.options.connectivity) {
      this.connectivityUnsub = this.options.connectivity.subscribe((state) => {
        if (state === 'online') {
          void this.syncPending().finally(() => {
            void this.rescheduleRetryTimer();
          });
        }
      });
    }
  }

  stopScheduler(): void {
    this.disposed = true;
    this.clearRetryTimer();
    this.connectivityUnsub?.();
    this.connectivityUnsub = null;
  }

  async enqueuePhotoAfterUpload(photoId: string, backendAssetId: string): Promise<void> {
    if (!this.isSyncEnabled()) {
      return;
    }
    try {
      await this.options.confirmed.setAssetIdForPhoto(photoId, backendAssetId);
      await this.options.confirmed.markPendingForPhotoWhenReady(photoId);
    } catch (e) {
      this.options.logger.warn('error', {
        where: 'authoritative_sync_enqueue',
        message: String(e),
      });
    }
    void this.syncPending()
      .catch(() => undefined)
      .finally(() => {
        void this.rescheduleRetryTimer();
      });
  }

  async syncPending(): Promise<AuthoritativeSyncSummary> {
    return this.runSyncPass({});
  }

  /** UI aisle action: only sync results belonging to this capture session. */
  async syncPendingForSession(sessionId: string): Promise<AuthoritativeSyncSummary> {
    const sid = (sessionId || '').trim();
    if (!sid) {
      return this.emptySummary();
    }
    return this.runSyncPass({ sessionId: sid });
  }

  /** UI selection: sync specific confirmed local result ids (same lease/idempotency path). */
  async syncResults(resultIds: readonly string[]): Promise<AuthoritativeSyncSummary> {
    const ids = [...new Set(resultIds.map((id) => (id || '').trim()).filter(Boolean))];
    if (ids.length === 0) {
      return this.emptySummary();
    }
    return this.runSyncPass({ resultIds: ids });
  }

  private async runSyncPass(filter: {
    sessionId?: string;
    resultIds?: readonly string[];
  }): Promise<AuthoritativeSyncSummary> {
    const empty = this.emptySummary();
    if (!this.isSyncEnabled() || this.pausedForCorruptDb) {
      return empty;
    }
    const nowMs = this.nowMs();
    if (nowMs < this.featureUnavailableUntil) {
      return empty;
    }
    if (this.running) {
      return empty;
    }
    this.running = true;
    const summary = this.emptySummary();
    let scheduleAfter = true;
    try {
      const now = new Date(nowMs).toISOString();
      await this.options.confirmed.recoverExpiredSyncLeases(now);
      let due = await this.options.confirmed.listDueForSync(now, SYNC_BATCH_MAX);
      if (filter.sessionId) {
        due = due.filter((row) => row.capture_session_id === filter.sessionId);
      }
      if (filter.resultIds && filter.resultIds.length > 0) {
        const allow = new Set(filter.resultIds);
        due = due.filter((row) => allow.has(row.id));
      }
      if (due.length === 0) {
        this.noProgressBackoffMs = 0;
        return summary;
      }
      emitObservability(this.options.reporter, {
        name: 'authoritative_sync_started',
        attributes: {
          pending_count: due.length,
          session_scoped: Boolean(filter.sessionId),
          result_scoped: Boolean(filter.resultIds?.length),
        },
      });

      const sessionCache = new Map<string, Promise<CaptureSessionRow | null>>();
      const workers = Math.min(SYNC_CONCURRENCY, due.length);
      let cursor = 0;
      const runOne = async () => {
        while (cursor < due.length) {
          const idx = cursor;
          cursor += 1;
          const row = due[idx]!;
          const outcome = await this.syncOne(row, sessionCache);
          summary.attempted += 1;
          summary[outcome] += 1;
        }
      };
      await Promise.all(Array.from({ length: workers }, () => runOne()));

      this.updateNoProgressBackoff(summary);
      emitObservability(this.options.reporter, {
        name: 'authoritative_sync_completed',
        attributes: { ...summary },
      });
      return summary;
    } catch (error) {
      if (isSqliteMalformedError(error)) {
        this.pausedForCorruptDb = true;
        scheduleAfter = false;
        this.clearRetryTimer();
        this.options.logger.warn('error', {
          where: 'authoritative_sync',
          code: 'LOCAL_DB_CORRUPTED',
          message: error instanceof Error ? error.message : String(error),
        });
      }
      throw error;
    } finally {
      this.running = false;
      if (scheduleAfter) {
        void this.rescheduleRetryTimer(summary);
      }
    }
  }

  private emptySummary(): AuthoritativeSyncSummary {
    return {
      attempted: 0,
      synced: 0,
      retry: 0,
      rejected: 0,
      conflict: 0,
      failed_terminal: 0,
      not_ready: 0,
      endpoint_missing: 0,
      skipped_lease: 0,
    };
  }

  private isSyncEnabled(): boolean {
    return this.options.flags.mobileAuthoritativeLocalCodeScan === true;
  }

  private nowMs(): number {
    return this.options.nowMs?.() ?? Date.now();
  }

  private clearRetryTimer(): void {
    if (this.retryTimer != null) {
      (this.options.clearTimeoutFn ?? clearTimeout)(this.retryTimer);
      this.retryTimer = null;
    }
  }

  async rescheduleRetryTimer(lastSummary?: AuthoritativeSyncSummary): Promise<void> {
    this.clearRetryTimer();
    if (!this.isSyncEnabled() || this.disposed || this.pausedForCorruptDb) {
      return;
    }
    let nextAt: string | null = null;
    try {
      nextAt = await this.options.confirmed.getEarliestSyncRetryAt();
    } catch (error) {
      if (isSqliteMalformedError(error)) {
        this.pausedForCorruptDb = true;
        this.options.logger.warn('error', {
          where: 'authoritative_sync_reschedule',
          code: 'LOCAL_DB_CORRUPTED',
          message: error instanceof Error ? error.message : String(error),
        });
        return;
      }
      throw error;
    }
    if (!nextAt) {
      return;
    }
    let delay = Math.max(0, Date.parse(nextAt) - this.nowMs());
    if (lastSummary && this.isNoProgressPass(lastSummary)) {
      delay = Math.max(delay, this.noProgressBackoffMs || AUTH_SYNC_NO_PROGRESS_MIN_DELAY_MS);
      this.options.logger.warn('recovery', {
        where: 'authoritative_sync_no_progress_backoff',
        delay_ms: delay,
        failed_terminal: lastSummary.failed_terminal,
        attempted: lastSummary.attempted,
      });
    }
    const capped = Math.min(delay, MAX_TIMER_DELAY_MS);
    this.retryTimer = (this.options.setTimeoutFn ?? setTimeout)(() => {
      void this.syncPending().catch(() => undefined);
    }, capped);
  }

  private isNoProgressPass(summary: AuthoritativeSyncSummary): boolean {
    return summary.attempted > 0 && summary.synced === 0 && summary.retry === 0;
  }

  private updateNoProgressBackoff(summary: AuthoritativeSyncSummary): void {
    if (summary.synced > 0 || summary.retry > 0) {
      this.noProgressBackoffMs = 0;
      return;
    }
    if (!this.isNoProgressPass(summary)) {
      return;
    }
    const next =
      this.noProgressBackoffMs === 0
        ? AUTH_SYNC_NO_PROGRESS_MIN_DELAY_MS
        : Math.min(this.noProgressBackoffMs * 2, AUTH_SYNC_NO_PROGRESS_MAX_DELAY_MS);
    this.noProgressBackoffMs = next;
  }

  private async getSessionCached(
    sessionId: string,
    cache: Map<string, Promise<CaptureSessionRow | null>>,
  ): Promise<CaptureSessionRow | null> {
    let pending = cache.get(sessionId);
    if (!pending) {
      pending = this.options.capture.getSession(sessionId);
      cache.set(sessionId, pending);
    }
    return pending;
  }

  private async syncOne(
    row: ConfirmedLocalResultRow,
    sessionCache: Map<string, Promise<CaptureSessionRow | null>>,
  ): Promise<AuthoritativeSyncOutcome> {
    const photo = await this.options.capture.getPhotoById(row.capture_photo_id);
    const session = photo
      ? await this.getSessionCached(photo.capture_session_id, sessionCache)
      : null;
    const now = new Date(this.nowMs()).toISOString();
    const assetId = photo?.backend_asset_id ?? row.asset_id;

    if (!session) {
      await this.options.confirmed.markNotReady(row.id, 'NOT_READY_SESSION', now);
      return 'not_ready';
    }
    if (!assetId) {
      await this.options.confirmed.markNotReady(row.id, 'NOT_READY_ASSET', now);
      return 'not_ready';
    }
    if (!row.client_file_id || !photo?.client_file_id) {
      await this.options.confirmed.markNotReady(row.id, 'NOT_READY_CLIENT_FILE', now);
      return 'not_ready';
    }
    if (!row.prepared_asset_sha256 || !row.confirmed_internal_code) {
      await this.options.confirmed.completeSyncTerminal(
        row.id,
        'FAILED_TERMINAL',
        'INVALID_LOCAL_RESULT',
        now,
      );
      return 'failed_terminal';
    }

    if (row.sync_attempt_count >= SYNC_MAX_ATTEMPTS) {
      await this.options.confirmed.completeSyncTerminal(
        row.id,
        'FAILED_TERMINAL',
        'SYNC_MAX_ATTEMPTS',
        now,
      );
      return 'failed_terminal';
    }

    const claimed = await this.options.confirmed.claimSyncLease(
      row.id,
      'lease',
      new Date(this.nowMs() + AUTH_SYNC_LEASE_MS).toISOString(),
      now,
    );
    if (!claimed) {
      return 'skipped_lease';
    }

    try {
      const response = await this.options.api.upsertResult(
        session.inventory_id,
        session.aisle_id,
        assetId,
        mapConfirmedToAuthoritativeRequest(row),
      );
      const ok = await this.options.confirmed.completeSyncSuccess(
        row.id,
        new Date(this.nowMs()).toISOString(),
        response.applied_at ?? null,
      );
      return ok ? 'synced' : 'skipped_lease';
    } catch (e) {
      const apiErr = e instanceof ApiError ? e : null;
      emitObservability(this.options.reporter, {
        name: 'authoritative_sync_item_failed',
        clientFileId: row.client_file_id ?? undefined,
        attributes: {
          result_id: row.id,
          http_status: apiErr?.status ?? null,
          error_code: apiErr?.code ?? String(e),
          attempt: row.sync_attempt_count,
        },
      });
      return this.handleSyncError(row, e);
    }
  }

  private async handleSyncError(
    row: ConfirmedLocalResultRow,
    error: unknown,
  ): Promise<AuthoritativeSyncOutcome> {
    const now = new Date(this.nowMs()).toISOString();
    const apiErr = error instanceof ApiError ? error : null;
    const classified = classifyAuthoritativeSyncError({
      status: apiErr?.status ?? null,
      code: apiErr?.code ?? null,
      attempt: row.sync_attempt_count,
      computeDelayMs: (attempt) =>
        computeRetryDelayMs({ attempt, baseDelayMs: 2_000 }),
    });

    if (classified.kind === 'rejected') {
      await this.options.confirmed.completeSyncTerminal(
        row.id,
        'REJECTED',
        classified.errorCode,
        now,
      );
      return 'rejected';
    }
    if (classified.kind === 'conflict') {
      await this.options.confirmed.completeSyncTerminal(
        row.id,
        'CONFLICT',
        classified.errorCode,
        now,
      );
      return 'conflict';
    }
    if (classified.kind === 'failed_terminal') {
      await this.options.confirmed.completeSyncTerminal(
        row.id,
        'FAILED_TERMINAL',
        classified.errorCode,
        now,
      );
      return 'failed_terminal';
    }
    if (classified.kind === 'endpoint_missing') {
      this.featureUnavailableUntil = this.nowMs() + classified.delayMs;
      await this.options.confirmed.resetToPending(row.id, classified.errorCode, now);
      return 'endpoint_missing';
    }
    if (classified.kind === 'pending_asset') {
      await this.options.confirmed.completeSyncRetry(
        row.id,
        classified.errorCode,
        new Date(this.nowMs() + classified.delayMs).toISOString(),
        now,
      );
      return 'retry';
    }
    if (classified.kind === 'retry') {
      await this.options.confirmed.completeSyncRetry(
        row.id,
        classified.errorCode,
        new Date(this.nowMs() + classified.delayMs).toISOString(),
        now,
      );
      return 'retry';
    }
    return 'failed_terminal';
  }
}
