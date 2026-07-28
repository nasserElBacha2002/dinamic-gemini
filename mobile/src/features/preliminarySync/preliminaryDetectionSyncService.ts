import { computeRetryDelayMs } from '../../core/uploadBackoff';
import type { FeatureFlags } from '../../core/featureFlags';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type {
  LocalDetectionDraftRepository,
  LocalDetectionDraftRow,
} from '../../database/repositories/localDetectionDraftRepository';
import { emitObservability, type ObservabilityReporter } from '../../observability';
import { ApiError } from '../../services/api/apiClient';
import type { ConnectivityService } from '../../services/connectivity/connectivity';
import { createId } from '../../shared/createId';
import type { CaptureSessionRow } from '../../database/schema/captureSchema';
import { mapDraftToPreliminarySyncRequest } from './preliminaryDraftPayloadMapper';
import type { PreliminaryDetectionApi } from './preliminaryDetectionApi';
import {
  classifyPreliminarySyncError,
  type PreliminarySyncOutcome,
} from './preliminarySyncOutcomeClassifier';

/** Must exceed API request timeout (default 20s) with margin. */
export const SYNC_LEASE_MS = 90_000;
export const SYNC_REQUEST_TIMEOUT_MS = 30_000;
const SYNC_BATCH_MAX = 20;
const SYNC_CONCURRENCY = 2;
const SYNC_MAX_ATTEMPTS = 8;
const LOCAL_SYNCED_RETENTION_DAYS = 14;
const LOCAL_TERMINAL_RETENTION_DAYS = 30;
const MAX_TIMER_DELAY_MS = 6 * 60 * 60_000;

export interface PreliminarySyncSummary {
  attempted: number;
  synced: number;
  retry: number;
  rejected: number;
  conflict: number;
  failed_terminal: number;
  not_ready: number;
  skipped_lease: number;
}

export interface PreliminaryDetectionSyncServiceOptions {
  readonly flags: FeatureFlags;
  readonly drafts: LocalDetectionDraftRepository;
  readonly capture: CaptureRepository;
  readonly api: PreliminaryDetectionApi;
  readonly logger: Logger;
  readonly reporter?: ObservabilityReporter | null;
  readonly connectivity?: ConnectivityService | null;
  readonly nowMs?: () => number;
  readonly setTimeoutFn?: typeof setTimeout;
  readonly clearTimeoutFn?: typeof clearTimeout;
}

/**
 * Syncs local CODE_SCAN drafts as non-authoritative diagnostic evidence.
 * Never blocks upload or POST /process.
 * Background WorkManager is intentionally not implemented — JS scheduler only.
 */
export class PreliminaryDetectionSyncService {
  private running = false;
  private featureUnavailableUntil = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private connectivityUnsub: (() => void) | null = null;
  private disposed = false;

  constructor(private readonly options: PreliminaryDetectionSyncServiceOptions) {}

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

  async enqueuePhotoAfterUpload(photoId: string): Promise<void> {
    if (!this.isSyncEnabled()) {
      return;
    }
    try {
      await this.options.drafts.markPendingForPhotoWhenReady(photoId);
    } catch (e) {
      this.options.logger.warn('error', {
        where: 'preliminary_sync_enqueue',
        message: String(e),
      });
    }
    void this.syncPending()
      .catch(() => undefined)
      .finally(() => {
        void this.rescheduleRetryTimer();
      });
  }

  async syncPending(): Promise<PreliminarySyncSummary> {
    const empty = this.emptySummary();
    if (!this.isSyncEnabled()) {
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
    try {
      const now = new Date(nowMs).toISOString();
      await this.options.drafts.recoverExpiredSyncLeases(now);
      await this.purgeRetention(nowMs);
      const due = await this.options.drafts.listDueForSync(now, SYNC_BATCH_MAX);
      if (due.length === 0) {
        return summary;
      }
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_started',
        attributes: { pending_count: due.length },
      });

      const sessionCache = new Map<string, Promise<CaptureSessionRow | null>>();
      const workers = Math.min(SYNC_CONCURRENCY, due.length);
      let cursor = 0;
      const runOne = async () => {
        while (cursor < due.length) {
          const idx = cursor;
          cursor += 1;
          const draft = due[idx]!;
          const outcome = await this.syncOne(draft, sessionCache);
          summary.attempted += 1;
          summary[outcome] += 1;
        }
      };
      await Promise.all(Array.from({ length: workers }, () => runOne()));

      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_completed',
        attributes: { ...summary },
      });
      return summary;
    } finally {
      this.running = false;
      void this.rescheduleRetryTimer();
    }
  }

  private emptySummary(): PreliminarySyncSummary {
    return {
      attempted: 0,
      synced: 0,
      retry: 0,
      rejected: 0,
      conflict: 0,
      failed_terminal: 0,
      not_ready: 0,
      skipped_lease: 0,
    };
  }

  private isSyncEnabled(): boolean {
    return this.options.flags.mobilePreliminaryDetectionSync === true;
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

  async rescheduleRetryTimer(): Promise<void> {
    this.clearRetryTimer();
    if (!this.isSyncEnabled() || this.disposed) {
      return;
    }
    const nextAt = await this.options.drafts.getEarliestSyncRetryAt();
    if (!nextAt) {
      return;
    }
    const delay = Math.max(0, Date.parse(nextAt) - this.nowMs());
    const capped = Math.min(delay, MAX_TIMER_DELAY_MS);
    this.retryTimer = (this.options.setTimeoutFn ?? setTimeout)(() => {
      void this.syncPending().catch(() => undefined);
    }, capped);
  }

  private async purgeRetention(nowMs: number): Promise<void> {
    const syncedCutoff = new Date(
      nowMs - LOCAL_SYNCED_RETENTION_DAYS * 24 * 60 * 60_000,
    ).toISOString();
    const terminalCutoff = new Date(
      nowMs - LOCAL_TERMINAL_RETENTION_DAYS * 24 * 60 * 60_000,
    ).toISOString();
    const purgedSynced = await this.options.drafts.purgeSyncedOlderThan(syncedCutoff);
    const purgedTerminal = await this.options.drafts.purgeTerminalOlderThan(terminalCutoff);
    if (purgedSynced || purgedTerminal) {
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_purged',
        attributes: { purged_synced: purgedSynced, purged_terminal: purgedTerminal },
      });
    }
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
    draft: LocalDetectionDraftRow,
    sessionCache: Map<string, Promise<CaptureSessionRow | null>>,
  ): Promise<PreliminarySyncOutcome> {
    const photo = await this.options.capture.getPhotoById(draft.capture_photo_id);
    const session = photo
      ? await this.getSessionCached(photo.capture_session_id, sessionCache)
      : null;
    const now = new Date(this.nowMs()).toISOString();

    if (!session) {
      await this.options.drafts.markNotReady(draft.id, 'NOT_READY_SESSION', now);
      return 'not_ready';
    }
    if (!photo?.backend_asset_id) {
      await this.options.drafts.markNotReady(draft.id, 'NOT_READY_ASSET', now);
      return 'not_ready';
    }
    if (!photo.client_file_id || !draft.client_file_id) {
      await this.options.drafts.markNotReady(draft.id, 'NOT_READY_CLIENT_FILE', now);
      return 'not_ready';
    }
    if (!draft.prepared_asset_fingerprint || !draft.detected_at) {
      const leaseToken = createId();
      const claimed = await this.options.drafts.claimSyncLease(
        draft.id,
        leaseToken,
        new Date(this.nowMs() + SYNC_LEASE_MS).toISOString(),
        now,
      );
      if (claimed) {
        await this.options.drafts.completeSyncTerminal(
          draft.id,
          leaseToken,
          'FAILED_TERMINAL',
          'INVALID_LOCAL_DRAFT',
          now,
        );
        return 'failed_terminal';
      }
      await this.options.drafts.markNotReady(draft.id, 'INVALID_LOCAL_DRAFT', now);
      return 'not_ready';
    }

    if (draft.sync_attempt_count >= SYNC_MAX_ATTEMPTS) {
      const leaseToken = createId();
      const claimed = await this.options.drafts.claimSyncLease(
        draft.id,
        leaseToken,
        new Date(this.nowMs() + SYNC_LEASE_MS).toISOString(),
        now,
      );
      if (claimed) {
        await this.options.drafts.completeSyncTerminal(
          draft.id,
          leaseToken,
          'FAILED_TERMINAL',
          'SYNC_MAX_ATTEMPTS',
          now,
        );
      }
      return 'failed_terminal';
    }

    const leaseToken = createId();
    const claimed = await this.options.drafts.claimSyncLease(
      draft.id,
      leaseToken,
      new Date(this.nowMs() + SYNC_LEASE_MS).toISOString(),
      now,
    );
    if (!claimed) {
      return 'skipped_lease';
    }

    try {
      const response = await this.options.api.upsertDraft(
        session.inventory_id,
        session.aisle_id,
        draft.id,
        mapDraftToPreliminarySyncRequest({
          draft,
          assetId: photo.backend_asset_id,
        }),
      );
      const ok = await this.options.drafts.completeSyncSuccess(
        draft.id,
        leaseToken,
        response.server_preliminary_id,
        response.received_at || new Date(this.nowMs()).toISOString(),
      );
      return ok ? 'synced' : 'skipped_lease';
    } catch (e) {
      return this.handleSyncError(draft, leaseToken, e);
    }
  }

  private async handleSyncError(
    draft: LocalDetectionDraftRow,
    leaseToken: string,
    error: unknown,
  ): Promise<PreliminarySyncOutcome> {
    const now = new Date(this.nowMs()).toISOString();
    const apiErr = error instanceof ApiError ? error : null;
    const classified = classifyPreliminarySyncError({
      status: apiErr?.status ?? null,
      code: apiErr?.code ?? null,
      attempt: draft.sync_attempt_count,
      computeDelayMs: (attempt) =>
        computeRetryDelayMs({ attempt, baseDelayMs: 2_000 }),
    });

    if (classified.kind === 'rejected') {
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_rejected',
        attributes: { draft_id: draft.id },
      });
      await this.options.drafts.completeSyncTerminal(
        draft.id,
        leaseToken,
        'REJECTED',
        classified.errorCode,
        now,
      );
      return 'rejected';
    }
    if (classified.kind === 'conflict') {
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_conflict',
        attributes: { draft_id: draft.id },
      });
      await this.options.drafts.completeSyncTerminal(
        draft.id,
        leaseToken,
        'CONFLICT',
        classified.errorCode,
        now,
      );
      return 'conflict';
    }
    if (classified.kind === 'failed_terminal') {
      await this.options.drafts.completeSyncTerminal(
        draft.id,
        leaseToken,
        'FAILED_TERMINAL',
        classified.errorCode,
        now,
      );
      return 'failed_terminal';
    }
    if (classified.kind === 'feature_unavailable') {
      this.featureUnavailableUntil = this.nowMs() + classified.delayMs;
      await this.options.drafts.completeSyncRetry(
        draft.id,
        leaseToken,
        classified.errorCode,
        new Date(this.featureUnavailableUntil).toISOString(),
        now,
      );
      return 'retry';
    }
    if (classified.kind === 'pending_asset' || classified.kind === 'retry') {
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_retry',
        attributes: { draft_id: draft.id, reason: classified.errorCode },
      });
      await this.options.drafts.completeSyncRetry(
        draft.id,
        leaseToken,
        classified.errorCode,
        new Date(this.nowMs() + classified.delayMs).toISOString(),
        now,
      );
      return 'retry';
    }
    return 'failed_terminal';
  }
}
