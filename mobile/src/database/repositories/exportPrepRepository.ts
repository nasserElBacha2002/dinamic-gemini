import type { SQLiteDatabase } from '../database';
import { runImmediateTransaction } from '../sqliteWriteGate';
import { createId } from '../../shared/createId';
import {
  EXPORT_PREP_STATUSES,
  type ExportPrepCounts,
  type ExportPrepJobRow,
  type ExportPrepStatus,
} from '../../features/exportPrep/exportPrepTypes';

type SQLiteBindValue = string | number | null;

export const LEASE_MS_DEFAULT = 120_000;

export class ExportPrepFenceError extends Error {
  readonly code = 'EXPORT_PREP_FENCE_LOST';
  constructor(message = 'Lease fencing failed — job owned by another worker') {
    super(message);
    this.name = 'ExportPrepFenceError';
  }
}

function nowIso(): string {
  return new Date().toISOString();
}

function isKnownStatus(status: string): status is ExportPrepStatus {
  return (EXPORT_PREP_STATUSES as readonly string[]).includes(status);
}

function requireKnownStatus(status: string): ExportPrepStatus {
  if (!isKnownStatus(status)) {
    throw new Error(`EXPORT_PREP_UNKNOWN_STATUS: ${status}`);
  }
  return status;
}

/** Pure hex SHA-256 (64 chars), no algorithm prefix. */
export function isValidStagedSha256(value: string | null | undefined): boolean {
  return typeof value === 'string' && /^[a-f0-9]{64}$/i.test(value.trim());
}

export class ExportPrepRepository {
  constructor(private readonly db: SQLiteDatabase) {}

  async getByPhotoId(capturePhotoId: string): Promise<ExportPrepJobRow | null> {
    const row = await this.db.getFirstAsync<ExportPrepJobRow>(
      `SELECT * FROM export_prep_jobs WHERE capture_photo_id = ?;`,
      capturePhotoId,
    );
    if (row) requireKnownStatus(row.status);
    return row;
  }

  async listForSession(sessionId: string): Promise<ExportPrepJobRow[]> {
    const rows = await this.db.getAllAsync<ExportPrepJobRow>(
      `SELECT * FROM export_prep_jobs
         WHERE capture_session_id = ?
         ORDER BY queued_at ASC;`,
      sessionId,
    );
    for (const row of rows) requireKnownStatus(row.status);
    return rows;
  }

  async countsForSession(sessionId: string): Promise<ExportPrepCounts> {
    const rows = await this.db.getAllAsync<{ status: string; c: number }>(
      `SELECT status, COUNT(*) AS c FROM export_prep_jobs
         WHERE capture_session_id = ?
         GROUP BY status;`,
      sessionId,
    );
    let queued = 0;
    let preparing = 0;
    let scanning = 0;
    let validating = 0;
    let ready = 0;
    let failedRetryable = 0;
    let failedTerminal = 0;
    let excluded = 0;
    let total = 0;
    let unknown = 0;
    for (const row of rows) {
      const n = Number(row.c) || 0;
      total += n;
      if (!isKnownStatus(row.status)) {
        unknown += n;
        continue;
      }
      switch (row.status) {
        case 'QUEUED':
          queued += n;
          break;
        case 'PREPARING':
          preparing += n;
          break;
        case 'SCANNING':
          scanning += n;
          break;
        case 'VALIDATING':
          validating += n;
          break;
        case 'READY':
          ready += n;
          break;
        case 'FAILED_RETRYABLE':
          failedRetryable += n;
          break;
        case 'FAILED_TERMINAL':
          failedTerminal += n;
          break;
        case 'EXCLUDED':
          excluded += n;
          break;
        default:
          break;
      }
    }
    const processing = preparing + scanning + validating;
    return {
      queued,
      preparing,
      scanning,
      validating,
      ready,
      failedRetryable,
      failedTerminal,
      excluded,
      processing,
      pending: queued + processing + unknown,
      failed: failedRetryable + failedTerminal,
      total,
    };
  }

  /**
   * Idempotent enqueue: inserts QUEUED or requeues FAILED_RETRYABLE / expired lease.
   * Does not touch READY / EXCLUDED / FAILED_TERMINAL / in-flight with valid lease.
   */
  async enqueueIdempotent(input: {
    readonly capturePhotoId: string;
    readonly captureSessionId: string;
    readonly sourceUri: string;
    readonly sourceFingerprint: string | null;
    readonly exportFileName: string | null;
  }): Promise<{ readonly created: boolean; readonly job: ExportPrepJobRow }> {
    const now = nowIso();
    return runImmediateTransaction(this.db, async () => {
      const existing = await this.getByPhotoId(input.capturePhotoId);
      if (existing) {
        if (existing.status === 'READY' || existing.status === 'EXCLUDED') {
          return { created: false, job: existing };
        }
        if (existing.status === 'FAILED_TERMINAL') {
          return { created: false, job: existing };
        }
        if (
          existing.status === 'PREPARING' ||
          existing.status === 'SCANNING' ||
          existing.status === 'VALIDATING'
        ) {
          const leaseOk =
            existing.lease_token != null &&
            existing.lease_expires_at != null &&
            existing.lease_expires_at > now;
          if (leaseOk) {
            return { created: false, job: existing };
          }
        }
        await this.db.runAsync(
          `UPDATE export_prep_jobs SET
             status = 'QUEUED',
             source_uri = ?,
             source_fingerprint = COALESCE(?, source_fingerprint),
             export_file_name = COALESCE(?, export_file_name),
             lease_token = NULL,
             lease_expires_at = NULL,
             error_code = NULL,
             error_message = NULL,
             updated_at = ?
           WHERE capture_photo_id = ?;`,
          input.sourceUri,
          input.sourceFingerprint,
          input.exportFileName,
          now,
          input.capturePhotoId,
        );
        const job = (await this.getByPhotoId(input.capturePhotoId))!;
        return { created: false, job };
      }
      await this.db.runAsync(
        `INSERT INTO export_prep_jobs (
           capture_photo_id, capture_session_id, status, source_uri, staging_uri,
           export_file_name, size_bytes, sha256, source_fingerprint, error_code, error_message,
           attempt_count, max_attempts, lease_token, lease_expires_at,
           queued_at, started_at, ready_at, updated_at, created_at
         ) VALUES (?, ?, 'QUEUED', ?, NULL, ?, NULL, NULL, ?, NULL, NULL, 0, 3, NULL, NULL, ?, NULL, NULL, ?, ?);`,
        input.capturePhotoId,
        input.captureSessionId,
        input.sourceUri,
        input.exportFileName,
        input.sourceFingerprint,
        now,
        now,
        now,
      );
      const job = (await this.getByPhotoId(input.capturePhotoId))!;
      return { created: true, job };
    });
  }

  /** Claim next work item. Returned job always has non-null lease_token. */
  async claimNext(
    sessionId: string | null,
    leaseMs: number = LEASE_MS_DEFAULT,
  ): Promise<ExportPrepJobRow | null> {
    const now = nowIso();
    const leaseToken = createId();
    const expires = new Date(Date.now() + leaseMs).toISOString();
    return runImmediateTransaction(this.db, async () => {
      const candidate = sessionId
        ? await this.db.getFirstAsync<ExportPrepJobRow>(
            `SELECT * FROM export_prep_jobs
               WHERE capture_session_id = ?
                 AND (
                   status = 'QUEUED'
                   OR (
                     status IN ('PREPARING', 'SCANNING', 'VALIDATING')
                     AND (lease_expires_at IS NULL OR lease_expires_at < ? OR lease_token IS NULL)
                   )
                   OR status = 'FAILED_RETRYABLE'
                 )
               ORDER BY
                 CASE status WHEN 'QUEUED' THEN 0 WHEN 'FAILED_RETRYABLE' THEN 1 ELSE 2 END,
                 queued_at ASC
               LIMIT 1;`,
            sessionId,
            now,
          )
        : await this.db.getFirstAsync<ExportPrepJobRow>(
            `SELECT * FROM export_prep_jobs
               WHERE status = 'QUEUED'
                  OR (
                    status IN ('PREPARING', 'SCANNING', 'VALIDATING')
                    AND (lease_expires_at IS NULL OR lease_expires_at < ? OR lease_token IS NULL)
                  )
                  OR status = 'FAILED_RETRYABLE'
               ORDER BY
                 CASE status WHEN 'QUEUED' THEN 0 WHEN 'FAILED_RETRYABLE' THEN 1 ELSE 2 END,
                 queued_at ASC
               LIMIT 1;`,
            now,
          );
      if (!candidate) return null;
      const result = await this.db.runAsync(
        `UPDATE export_prep_jobs SET
           status = 'PREPARING',
           lease_token = ?,
           lease_expires_at = ?,
           attempt_count = attempt_count + 1,
           started_at = COALESCE(started_at, ?),
           updated_at = ?,
           error_code = NULL,
           error_message = NULL
         WHERE capture_photo_id = ?
           AND (
             status = 'QUEUED'
             OR status = 'FAILED_RETRYABLE'
             OR (
               status IN ('PREPARING', 'SCANNING', 'VALIDATING')
               AND (lease_expires_at IS NULL OR lease_expires_at < ? OR lease_token IS NULL)
             )
           );`,
        leaseToken,
        expires,
        now,
        now,
        candidate.capture_photo_id,
        now,
      );
      if ((result.changes ?? 0) !== 1) {
        return null;
      }
      const job = await this.getByPhotoId(candidate.capture_photo_id);
      if (!job?.lease_token) {
        throw new ExportPrepFenceError('claimNext returned job without lease_token');
      }
      return job;
    });
  }

  private async fencedUpdate(
    capturePhotoId: string,
    leaseToken: string,
    sql: string,
    params: SQLiteBindValue[],
  ): Promise<void> {
    const result = await this.db.runAsync(sql, ...params);
    if ((result.changes ?? 0) !== 1) {
      throw new ExportPrepFenceError(
        `fenced update failed for ${capturePhotoId} (lease=${leaseToken.slice(0, 8)}…)`,
      );
    }
  }

  async renewLease(
    capturePhotoId: string,
    leaseToken: string,
    leaseMs: number = LEASE_MS_DEFAULT,
  ): Promise<void> {
    const expires = new Date(Date.now() + leaseMs).toISOString();
    const now = nowIso();
    await this.fencedUpdate(
      capturePhotoId,
      leaseToken,
      `UPDATE export_prep_jobs SET lease_expires_at = ?, updated_at = ?
         WHERE capture_photo_id = ? AND lease_token = ?
           AND status IN ('PREPARING', 'SCANNING', 'VALIDATING');`,
      [expires, now, capturePhotoId, leaseToken],
    );
  }

  async markScanning(
    capturePhotoId: string,
    leaseToken: string,
    patch: {
      readonly stagingUri: string;
      readonly exportFileName: string;
      readonly sizeBytes: number;
      readonly renewLeaseMs?: number;
    },
  ): Promise<void> {
    const now = nowIso();
    const expires = new Date(Date.now() + (patch.renewLeaseMs ?? LEASE_MS_DEFAULT)).toISOString();
    await this.fencedUpdate(
      capturePhotoId,
      leaseToken,
      `UPDATE export_prep_jobs SET
         status = 'SCANNING',
         staging_uri = ?,
         export_file_name = ?,
         size_bytes = ?,
         lease_expires_at = ?,
         updated_at = ?
       WHERE capture_photo_id = ? AND lease_token = ?
         AND status = 'PREPARING';`,
      [
        patch.stagingUri,
        patch.exportFileName,
        patch.sizeBytes,
        expires,
        now,
        capturePhotoId,
        leaseToken,
      ],
    );
  }

  async markValidating(
    capturePhotoId: string,
    leaseToken: string,
    renewLeaseMs: number = LEASE_MS_DEFAULT,
  ): Promise<void> {
    const now = nowIso();
    const expires = new Date(Date.now() + renewLeaseMs).toISOString();
    await this.fencedUpdate(
      capturePhotoId,
      leaseToken,
      `UPDATE export_prep_jobs SET
         status = 'VALIDATING',
         lease_expires_at = ?,
         updated_at = ?
       WHERE capture_photo_id = ? AND lease_token = ?
         AND status = 'SCANNING';`,
      [expires, now, capturePhotoId, leaseToken],
    );
  }

  async markReady(
    capturePhotoId: string,
    leaseToken: string,
    patch: {
      readonly stagingUri: string;
      readonly exportFileName: string;
      readonly sizeBytes: number;
      readonly sha256: string;
    },
  ): Promise<void> {
    if (!patch.stagingUri || !patch.exportFileName) {
      throw new Error('EXPORT_PREP_READY_INCOMPLETE: staging_uri/export_file_name required');
    }
    if (!(patch.sizeBytes > 0)) {
      throw new Error('EXPORT_PREP_READY_INCOMPLETE: size_bytes required');
    }
    if (!isValidStagedSha256(patch.sha256)) {
      throw new Error('EXPORT_PREP_READY_INCOMPLETE: sha256 must be 64 hex chars');
    }
    const now = nowIso();
    await this.fencedUpdate(
      capturePhotoId,
      leaseToken,
      `UPDATE export_prep_jobs SET
         status = 'READY',
         staging_uri = ?,
         export_file_name = ?,
         size_bytes = ?,
         sha256 = ?,
         error_code = NULL,
         error_message = NULL,
         lease_token = NULL,
         lease_expires_at = NULL,
         ready_at = ?,
         updated_at = ?
       WHERE capture_photo_id = ? AND lease_token = ?
         AND status = 'VALIDATING';`,
      [
        patch.stagingUri,
        patch.exportFileName,
        patch.sizeBytes,
        patch.sha256.trim().toLowerCase(),
        now,
        now,
        capturePhotoId,
        leaseToken,
      ],
    );
  }

  /** Worker-owned failure — requires matching lease. */
  async markFailedFenced(
    capturePhotoId: string,
    leaseToken: string,
    errorCode: string,
    errorMessage: string,
  ): Promise<ExportPrepStatus> {
    const job = await this.getByPhotoId(capturePhotoId);
    if (!job) return 'FAILED_TERMINAL';
    if (job.lease_token !== leaseToken) {
      throw new ExportPrepFenceError('markFailedFenced: lease mismatch');
    }
    const terminal = job.attempt_count >= job.max_attempts;
    const status: ExportPrepStatus = terminal ? 'FAILED_TERMINAL' : 'FAILED_RETRYABLE';
    const now = nowIso();
    await this.fencedUpdate(
      capturePhotoId,
      leaseToken,
      `UPDATE export_prep_jobs SET
         status = ?,
         error_code = ?,
         error_message = ?,
         lease_token = NULL,
         lease_expires_at = NULL,
         updated_at = ?
       WHERE capture_photo_id = ? AND lease_token = ?
         AND status IN ('PREPARING', 'SCANNING', 'VALIDATING');`,
      [status, errorCode, errorMessage, now, capturePhotoId, leaseToken],
    );
    return status;
  }

  /** Operator / UI exclusion — invalidates any active lease. */
  async markExcluded(capturePhotoId: string): Promise<void> {
    const now = nowIso();
    await this.db.runAsync(
      `UPDATE export_prep_jobs SET
         status = 'EXCLUDED',
         lease_token = NULL,
         lease_expires_at = NULL,
         error_code = NULL,
         error_message = NULL,
         updated_at = ?
       WHERE capture_photo_id = ?;`,
      now,
      capturePhotoId,
    );
  }

  async invalidateReady(
    capturePhotoId: string,
    errorCode: string,
    errorMessage: string,
  ): Promise<void> {
    const now = nowIso();
    await this.db.runAsync(
      `UPDATE export_prep_jobs SET
         staging_uri = NULL, size_bytes = NULL, sha256 = NULL,
         status = 'FAILED_RETRYABLE', error_code = ?, error_message = ?,
         lease_token = NULL, lease_expires_at = NULL, ready_at = NULL, updated_at = ?
       WHERE capture_photo_id = ? AND status = 'READY';`,
      errorCode,
      errorMessage,
      now,
      capturePhotoId,
    );
  }

  async requeueFailed(capturePhotoId: string): Promise<void> {
    const now = nowIso();
    await this.db.runAsync(
      `UPDATE export_prep_jobs SET
         status = 'QUEUED',
         lease_token = NULL,
         lease_expires_at = NULL,
         error_code = NULL,
         error_message = NULL,
         updated_at = ?
       WHERE capture_photo_id = ?
         AND status IN ('FAILED_RETRYABLE', 'FAILED_TERMINAL');`,
      now,
      capturePhotoId,
    );
  }

  async requeueFromExcluded(capturePhotoId: string): Promise<void> {
    const now = nowIso();
    await this.db.runAsync(
      `UPDATE export_prep_jobs SET
         status = 'QUEUED',
         lease_token = NULL,
         lease_expires_at = NULL,
         error_code = NULL,
         error_message = NULL,
         ready_at = NULL,
         updated_at = ?
       WHERE capture_photo_id = ? AND status = 'EXCLUDED';`,
      now,
      capturePhotoId,
    );
  }

  /**
   * Operator reinclude fast-path: QUEUED → READY when staging/hash/size/name are already valid.
   * Not a worker path (no lease). Returns true if promoted.
   */
  async promoteQueuedToReadyIfComplete(capturePhotoId: string): Promise<boolean> {
    const job = await this.getByPhotoId(capturePhotoId);
    if (!job || job.status !== 'QUEUED') return false;
    if (
      !job.staging_uri ||
      !job.export_file_name ||
      !(job.size_bytes && job.size_bytes > 0) ||
      !isValidStagedSha256(job.sha256)
    ) {
      return false;
    }
    const now = nowIso();
    const result = await this.db.runAsync(
      `UPDATE export_prep_jobs SET
         status = 'READY',
         lease_token = NULL,
         lease_expires_at = NULL,
         ready_at = ?,
         updated_at = ?,
         error_code = NULL,
         error_message = NULL
       WHERE capture_photo_id = ?
         AND status = 'QUEUED'
         AND staging_uri IS NOT NULL
         AND sha256 IS NOT NULL
         AND size_bytes > 0
         AND export_file_name IS NOT NULL;`,
      now,
      now,
      capturePhotoId,
    );
    return (result.changes ?? 0) === 1;
  }

  async requeueAllFailedForSession(sessionId: string): Promise<number> {
    const now = nowIso();
    const result = await this.db.runAsync(
      `UPDATE export_prep_jobs SET
         status = 'QUEUED',
         lease_token = NULL,
         lease_expires_at = NULL,
         error_code = NULL,
         error_message = NULL,
         attempt_count = 0,
         updated_at = ?
       WHERE capture_session_id = ?
         AND status IN ('FAILED_RETRYABLE', 'FAILED_TERMINAL');`,
      now,
      sessionId,
    );
    return result.changes ?? 0;
  }

  async recoverInterrupted(): Promise<number> {
    const now = nowIso();
    const result = await this.db.runAsync(
      `UPDATE export_prep_jobs SET
         status = 'QUEUED',
         lease_token = NULL,
         lease_expires_at = NULL,
         updated_at = ?
       WHERE status IN ('PREPARING', 'SCANNING', 'VALIDATING');`,
      now,
    );
    return result.changes ?? 0;
  }

  async deleteForSession(sessionId: string): Promise<void> {
    await this.db.runAsync(`DELETE FROM export_prep_jobs WHERE capture_session_id = ?;`, sessionId);
  }
}
