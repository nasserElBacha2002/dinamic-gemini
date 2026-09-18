/**
 * Coordinated session artifact purge (Phase 6 corrections).
 * Order: close admission → abort export → drain prep → CANCELLED → files → metadata.
 * Never deletes metadata while file delete failed; durable PURGE_PENDING for retry.
 */

import * as FileSystem from 'expo-file-system';

import type { Logger } from '../../core/logging';
import type { ExportPrepQueue } from './exportPrepQueue';
import type { LocalExportAttemptRepository } from '../../database/repositories/localExportAttemptRepository';
import {
  resolveZipUri,
  type LocalCsvExportRepository,
} from '../../database/repositories/localCsvExportRepository';
import type { SessionPurgeTaskRepository } from '../../database/repositories/sessionPurgeTaskRepository';
import { deleteSessionExportStaging } from './exportStaging';
import {
  assertSafeSandboxDeleteTarget,
  type SandboxRoots,
} from './safeSandboxPath';
import {
  cleanupOutcomeLabel,
  emptyCleanupResult,
  type CleanupError,
  type CleanupResult,
} from './cleanupTypes';

export interface SessionArtifactPurgeCoordinatorDeps {
  readonly exportPrepQueue?: ExportPrepQueue | null;
  readonly attemptRepo?: LocalExportAttemptRepository | null;
  readonly exportRepo?: LocalCsvExportRepository | null;
  readonly purgeTaskRepo?: SessionPurgeTaskRepository | null;
  readonly logger?: Logger | null;
  readonly getRoots?: () => SandboxRoots;
  readonly cancelActiveExport?: (sessionId: string) => Promise<void>;
  readonly closeAdmission?: (sessionId: string) => void;
}

const purgingSessions = new Set<string>();

function defaultRoots(): SandboxRoots {
  return {
    documentDirectory: FileSystem.documentDirectory,
    cacheDirectory: FileSystem.cacheDirectory,
  };
}

export class SessionArtifactPurgeCoordinator {
  constructor(private readonly deps: SessionArtifactPurgeCoordinatorDeps) {}

  async purgeSession(sessionId: string): Promise<CleanupResult> {
    const started = Date.now();
    if (!sessionId) {
      return {
        ...emptyCleanupResult(started),
        failed: 1,
        errors: [
          {
            code: 'INVALID_SESSION',
            artifactType: 'unknown',
            operation: 'purge',
            recoverable: false,
          },
        ],
      };
    }

    if (purgingSessions.has(sessionId)) {
      return {
        ...emptyCleanupResult(started),
        skippedActive: 1,
        errors: [
          {
            code: 'PURGE_IN_PROGRESS',
            artifactType: 'unknown',
            operation: 'purge',
            recoverable: true,
            sessionRef: sessionId.slice(0, 8),
          },
        ],
      };
    }

    purgingSessions.add(sessionId);
    const errors: CleanupError[] = [];
    let deleted = 0;
    let scanned = 0;
    const sessionRef = sessionId.slice(0, 8);
    const roots = this.deps.getRoots?.() ?? defaultRoots();
    this.deps.logger?.info('storage.purge_started', { sessionRef });

    try {
      // 1) Close admission
      this.deps.closeAdmission?.(sessionId);

      // 2) Abort export and wait
      if (this.deps.cancelActiveExport) {
        try {
          await this.deps.cancelActiveExport(sessionId);
        } catch (error) {
          errors.push({
            code: 'CANCEL_EXPORT_FAILED',
            artifactType: 'unknown',
            operation: 'cancel_export',
            recoverable: true,
            sessionRef,
            message: error instanceof Error ? error.message : String(error),
          });
        }
      }

      // 3) Cancel + drain prep workers
      if (this.deps.exportPrepQueue) {
        try {
          await this.deps.exportPrepQueue.cancelAndDrainSession(sessionId);
        } catch (error) {
          errors.push({
            code: 'CANCEL_PREP_DRAIN_FAILED',
            artifactType: 'staging_ready',
            operation: 'cancel_drain',
            recoverable: true,
            sessionRef,
            message: error instanceof Error ? error.message : String(error),
          });
        }
      }

      // 4) Collect pending URIs before any metadata delete
      const pendingUris = await this.collectPendingUris(sessionId);
      if (this.deps.purgeTaskRepo) {
        await this.deps.purgeTaskRepo.upsertPending(sessionId, pendingUris);
      }

      // 5) Durable CANCELLED on active attempts
      if (this.deps.attemptRepo) {
        try {
          const active = await this.deps.attemptRepo.listActiveForSession(sessionId);
          for (const a of active) {
            try {
              await this.deps.attemptRepo.transitionState(a.id, 'CANCELLED', {
                completed_at: new Date().toISOString(),
                error_code: 'SESSION_PURGED',
              });
            } catch {
              // already terminal
            }
          }
        } catch (error) {
          errors.push({
            code: 'CANCEL_ATTEMPTS_FAILED',
            artifactType: 'unknown',
            operation: 'cancel_attempts',
            recoverable: true,
            sessionRef,
            message: error instanceof Error ? error.message : String(error),
          });
        }
      }

      // 6) Physical deletes — keep URI in pending on failure
      const remaining: string[] = [];
      for (const uri of pendingUris) {
        scanned += 1;
        const ok = await this.safeDeleteUri(uri, roots, errors, sessionRef);
        if (ok) deleted += 1;
        else remaining.push(uri);
      }

      // Staging dir
      try {
        if (this.deps.exportPrepQueue) {
          try {
            await this.deps.exportPrepQueue.purgeSessionArtifacts(sessionId);
            deleted += 1;
          } catch (error) {
            // Do not hide: try staging alone, still report partial
            try {
              await deleteSessionExportStaging(sessionId);
              deleted += 1;
              errors.push({
                code: 'PURGE_PREP_PARTIAL',
                artifactType: 'staging_ready',
                operation: 'purge_prep',
                recoverable: true,
                sessionRef,
                message: error instanceof Error ? error.message : String(error),
              });
            } catch (stagingError) {
              errors.push({
                code: 'PURGE_STAGING_FAILED',
                artifactType: 'staging_ready',
                operation: 'purge_staging',
                recoverable: true,
                sessionRef,
                message:
                  stagingError instanceof Error
                    ? stagingError.message
                    : String(stagingError),
              });
              remaining.push(`staging:${sessionId}`);
            }
          }
        } else {
          await deleteSessionExportStaging(sessionId);
          deleted += 1;
        }
      } catch (error) {
        errors.push({
          code: 'PURGE_STAGING_FAILED',
          artifactType: 'staging_ready',
          operation: 'purge_staging',
          recoverable: true,
          sessionRef,
          message: error instanceof Error ? error.message : String(error),
        });
        remaining.push(`staging:${sessionId}`);
      }

      // 7) Metadata only when no remaining files
      if (remaining.length === 0 && errors.filter((e) => e.code.includes('FAILED')).length === 0) {
        if (this.deps.attemptRepo) {
          await this.deps.attemptRepo.deleteForSession(sessionId);
        }
        if (this.deps.exportRepo) {
          await this.deps.exportRepo.deleteForSession(sessionId);
        }
        if (this.deps.purgeTaskRepo) {
          await this.deps.purgeTaskRepo.markComplete(sessionId);
        }
      } else {
        if (this.deps.purgeTaskRepo) {
          await this.deps.purgeTaskRepo.markPartial(
            sessionId,
            remaining,
            errors.map((e) => e.code).join(',') || 'PURGE_PARTIAL',
          );
        }
      }

      const result: CleanupResult = {
        scanned,
        deleted,
        quarantined: 0,
        recovered: 0,
        invalidated: 0,
        skippedActive: 0,
        failed: errors.length,
        errors,
        durationMs: Date.now() - started,
      };
      const label = cleanupOutcomeLabel(result);
      this.deps.logger?.info(
        label === 'completed' ? 'storage.purge_completed' : 'storage.purge_partial',
        {
          sessionRef,
          deleted: result.deleted,
          failed: result.failed,
          remaining: remaining.length,
          durationMs: result.durationMs,
        },
      );
      return result;
    } finally {
      purgingSessions.delete(sessionId);
    }
  }

  /** Resume incomplete purges after restart. */
  async resumePendingPurges(limit = 20): Promise<CleanupResult> {
    const started = Date.now();
    if (!this.deps.purgeTaskRepo) return emptyCleanupResult(started);
    const tasks = await this.deps.purgeTaskRepo.listIncomplete(limit);
    const parts: CleanupResult[] = [];
    for (const task of tasks) {
      parts.push(await this.purgeSession(task.capture_session_id));
    }
    if (parts.length === 0) return emptyCleanupResult(started);
    let scanned = 0;
    let deleted = 0;
    let failed = 0;
    const errors: CleanupError[] = [];
    for (const p of parts) {
      scanned += p.scanned;
      deleted += p.deleted;
      failed += p.failed;
      errors.push(...p.errors);
    }
    return {
      scanned,
      deleted,
      quarantined: 0,
      recovered: 0,
      invalidated: 0,
      skippedActive: 0,
      failed,
      errors,
      durationMs: Date.now() - started,
    };
  }

  private async collectPendingUris(sessionId: string): Promise<string[]> {
    const uris = new Set<string>();
    if (this.deps.attemptRepo) {
      const attempts = await this.deps.attemptRepo.listBySession(sessionId);
      for (const a of attempts) {
        if (a.tmp_csv_uri) uris.add(a.tmp_csv_uri);
        if (a.tmp_zip_uri) uris.add(a.tmp_zip_uri);
        if (a.final_csv_uri) uris.add(a.final_csv_uri);
        if (a.final_zip_uri) uris.add(a.final_zip_uri);
      }
    }
    if (this.deps.exportRepo) {
      const exports = await this.deps.exportRepo.listForSession(sessionId);
      for (const e of exports) {
        if (e.file_uri) uris.add(e.file_uri);
        const zip = resolveZipUri(e);
        if (zip) uris.add(zip);
      }
    }
    if (this.deps.purgeTaskRepo) {
      const existing = await this.deps.purgeTaskRepo.get(sessionId);
      if (existing) {
        for (const u of this.deps.purgeTaskRepo.parsePendingUris(existing)) {
          if (!u.startsWith('staging:')) uris.add(u);
        }
      }
    }
    return [...uris];
  }

  private async safeDeleteUri(
    uri: string,
    roots: SandboxRoots,
    errors: CleanupError[],
    sessionRef: string,
  ): Promise<boolean> {
    try {
      assertSafeSandboxDeleteTarget(uri, roots, {
        allowedPrefixes: ['aisle-exports/', 'export-staging/', 'export-quarantine/'],
        allowSessionDirDelete: true,
      });
      const info = await FileSystem.getInfoAsync(uri);
      if (!info.exists) return true;
      await FileSystem.deleteAsync(uri, { idempotent: true });
      return true;
    } catch (error) {
      errors.push({
        code: 'DELETE_EXPORT_FILE_FAILED',
        artifactType: 'zip_final',
        operation: 'delete_file',
        recoverable: true,
        sessionRef,
        message: error instanceof Error ? error.message : String(error),
      });
      return false;
    }
  }
}
