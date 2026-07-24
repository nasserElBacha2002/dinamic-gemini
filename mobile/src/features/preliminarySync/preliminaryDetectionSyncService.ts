import { computeRetryDelayMs } from '../../core/uploadBackoff';
import type { FeatureFlags } from '../../core/featureFlags';
import type { Logger } from '../../core/logging';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import type {
  LocalDetectionDraftRepository,
  LocalDetectionDraftRow,
} from '../../database/repositories/localDetectionDraftRepository';
import { emitObservability, type ObservabilityReporter } from '../../observability';
import { ApiError, REQUEST_TIMEOUT } from '../../services/api/apiClient';
import { createId } from '../../shared/createId';
import type { PreliminaryDetectionApi } from './preliminaryDetectionApi';

const SYNC_BATCH_MAX = 20;
const SYNC_CONCURRENCY = 2;
const SYNC_LEASE_MS = 60_000;
const SYNC_MAX_ATTEMPTS = 8;

export interface PreliminarySyncSummary {
  attempted: number;
  synced: number;
  retried: number;
  rejected: number;
  conflicted: number;
  skipped: number;
}

export interface PreliminaryDetectionSyncServiceOptions {
  readonly flags: FeatureFlags;
  readonly drafts: LocalDetectionDraftRepository;
  readonly capture: CaptureRepository;
  readonly api: PreliminaryDetectionApi;
  readonly logger: Logger;
  readonly reporter?: ObservabilityReporter | null;
}

/**
 * Syncs local CODE_SCAN drafts as non-authoritative diagnostic evidence.
 * Never blocks upload or POST /process.
 */
export class PreliminaryDetectionSyncService {
  private running = false;
  private featureUnavailableUntil = 0;

  constructor(private readonly options: PreliminaryDetectionSyncServiceOptions) {}

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
    void this.syncPending().catch(() => {
      // never surface to upload path
    });
  }

  async syncPending(): Promise<PreliminarySyncSummary> {
    const empty: PreliminarySyncSummary = {
      attempted: 0,
      synced: 0,
      retried: 0,
      rejected: 0,
      conflicted: 0,
      skipped: 0,
    };
    if (!this.isSyncEnabled()) {
      return empty;
    }
    if (Date.now() < this.featureUnavailableUntil) {
      return { ...empty, skipped: 1 };
    }
    if (this.running) {
      return empty;
    }
    this.running = true;
    const summary: PreliminarySyncSummary = { ...empty };
    try {
      const now = new Date().toISOString();
      await this.options.drafts.recoverExpiredSyncLeases(now);
      const due = await this.options.drafts.listDueForSync(now, SYNC_BATCH_MAX);
      if (due.length === 0) {
        return summary;
      }
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_started',
        attributes: { pending_count: due.length },
      });

      const workers = Math.min(SYNC_CONCURRENCY, due.length);
      let cursor = 0;
      const runOne = async () => {
        while (cursor < due.length) {
          const idx = cursor;
          cursor += 1;
          const draft = due[idx]!;
          const outcome = await this.syncOne(draft);
          summary.attempted += 1;
          if (outcome === 'synced') summary.synced += 1;
          else if (outcome === 'retry') summary.retried += 1;
          else if (outcome === 'rejected') summary.rejected += 1;
          else if (outcome === 'conflict') summary.conflicted += 1;
          else summary.skipped += 1;
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
    }
  }

  private isSyncEnabled(): boolean {
    return this.options.flags.mobilePreliminaryDetectionSync === true;
  }

  private async syncOne(
    draft: LocalDetectionDraftRow,
  ): Promise<'synced' | 'retry' | 'rejected' | 'conflict' | 'skipped'> {
    const photo = await this.options.capture.getPhotoById(draft.capture_photo_id);
    const session = photo ? await this.options.capture.getSession(photo.capture_session_id) : null;
    if (!photo?.backend_asset_id || !photo.client_file_id || !session) {
      return 'skipped';
    }
    if (!draft.prepared_asset_fingerprint || !draft.client_file_id) {
      return 'skipped';
    }
    if (draft.sync_attempt_count >= SYNC_MAX_ATTEMPTS) {
      const leaseToken = createId();
      const now = new Date().toISOString();
      const claimed = await this.options.drafts.claimSyncLease(
        draft.id,
        leaseToken,
        new Date(Date.now() + SYNC_LEASE_MS).toISOString(),
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
      return 'rejected';
    }

    const leaseToken = createId();
    const now = new Date().toISOString();
    const claimed = await this.options.drafts.claimSyncLease(
      draft.id,
      leaseToken,
      new Date(Date.now() + SYNC_LEASE_MS).toISOString(),
      now,
    );
    if (!claimed) {
      return 'skipped';
    }

    try {
      const response = await this.options.api.upsertDraft(
        session.inventory_id,
        session.aisle_id,
        draft.id,
        {
          schema_version: '1',
          capture_session_id: draft.capture_session_id,
          capture_photo_id: draft.capture_photo_id,
          client_file_id: draft.client_file_id,
          asset_id: photo.backend_asset_id,
          processing_mode: 'CODE_SCAN',
          status: draft.status,
          internal_code: draft.internal_code,
          quantity: draft.quantity,
          quantity_status: draft.quantity_status,
          detected_format: draft.detected_format,
          detected_symbology: draft.detected_symbology,
          candidate_count: draft.candidate_count,
          parser_version: draft.parser_version,
          detector_version: draft.detector_version,
          prepared_asset_sha256: draft.prepared_asset_fingerprint,
          payload_hash: draft.raw_value_hash,
          processing_ms: draft.processing_ms,
          detected_at: draft.updated_at,
        },
      );
      const ok = await this.options.drafts.completeSyncSuccess(
        draft.id,
        leaseToken,
        response.server_preliminary_id,
        response.received_at || new Date().toISOString(),
      );
      return ok ? 'synced' : 'skipped';
    } catch (e) {
      return this.handleSyncError(draft, leaseToken, e);
    }
  }

  private async handleSyncError(
    draft: LocalDetectionDraftRow,
    leaseToken: string,
    error: unknown,
  ): Promise<'synced' | 'retry' | 'rejected' | 'conflict' | 'skipped'> {
    const now = new Date().toISOString();
    const apiErr = error instanceof ApiError ? error : null;
    const status = apiErr?.status ?? null;
    const code = apiErr?.code ?? (error instanceof Error ? error.message : 'SYNC_ERROR');

    if (status === 422) {
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_rejected',
        attributes: { draft_id: draft.id, http_status: 422 },
      });
      await this.options.drafts.completeSyncTerminal(draft.id, leaseToken, 'REJECTED', 'HTTP_422', now);
      return 'rejected';
    }
    if (status === 409) {
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_conflict',
        attributes: { draft_id: draft.id },
      });
      await this.options.drafts.completeSyncTerminal(draft.id, leaseToken, 'CONFLICT', 'HTTP_409', now);
      return 'conflict';
    }
    if (status === 403) {
      await this.options.drafts.completeSyncTerminal(draft.id, leaseToken, 'FAILED_TERMINAL', 'HTTP_403', now);
      return 'rejected';
    }
    if (status === 404 || status === 405) {
      const detail = String(apiErr?.message ?? '');
      if (
        detail.toLowerCase().includes('not enabled') ||
        (detail.toLowerCase().includes('not found') &&
          detail.toLowerCase().includes('preliminary'))
      ) {
        this.featureUnavailableUntil = Date.now() + 15 * 60_000;
        await this.options.drafts.completeSyncRetry(
          draft.id,
          leaseToken,
          'FEATURE_UNAVAILABLE',
          new Date(this.featureUnavailableUntil).toISOString(),
          now,
        );
        return 'retry';
      }
      // Asset not ready yet
      await this.options.drafts.completeSyncRetry(
        draft.id,
        leaseToken,
        'PENDING_ASSET',
        new Date(Date.now() + 30_000).toISOString(),
        now,
      );
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_retry',
        attributes: { draft_id: draft.id, reason: 'PENDING_ASSET' },
      });
      return 'retry';
    }
    if (status === 401) {
      // ApiClient already refreshes once; treat as retryable.
      await this.options.drafts.completeSyncRetry(
        draft.id,
        leaseToken,
        'HTTP_401',
        new Date(
          Date.now() +
            computeRetryDelayMs({ attempt: draft.sync_attempt_count, baseDelayMs: 2_000 }),
        ).toISOString(),
        now,
      );
      return 'retry';
    }
    if (
      status === 429 ||
      (status != null && status >= 500) ||
      code === REQUEST_TIMEOUT ||
      status === null
    ) {
      await this.options.drafts.completeSyncRetry(
        draft.id,
        leaseToken,
        status != null ? `HTTP_${status}` : String(code),
        new Date(
          Date.now() +
            computeRetryDelayMs({ attempt: draft.sync_attempt_count, baseDelayMs: 2_000 }),
        ).toISOString(),
        now,
      );
      emitObservability(this.options.reporter, {
        name: 'preliminary_sync_retry',
        attributes: { draft_id: draft.id, http_status: status },
      });
      return 'retry';
    }

    await this.options.drafts.completeSyncTerminal(
      draft.id,
      leaseToken,
      'FAILED_TERMINAL',
      `HTTP_${status ?? 'UNKNOWN'}`,
      now,
    );
    return 'rejected';
  }
}
