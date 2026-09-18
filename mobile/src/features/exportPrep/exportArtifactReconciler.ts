/**
 * Reconcile sandbox files ↔ SQLite for export artifacts (Phase 6).
 * Prefer validate → recover → quarantine → delete-only-when-safe.
 */

import * as FileSystem from 'expo-file-system';

import type { Logger } from '../../core/logging';
import type { ExportPrepRepository } from '../../database/repositories/exportPrepRepository';
import type { LocalCsvExportRepository } from '../../database/repositories/localCsvExportRepository';
import type { LocalExportAttemptRepository } from '../../database/repositories/localExportAttemptRepository';
import type { CaptureRepository } from '../../database/repositories/captureRepository';
import {
  DEFAULT_ARTIFACT_RETENTION_TTLS,
  decideArtifactRetention,
  isActiveExportAttemptState,
  type ArtifactRetentionTtls,
} from './artifactRetentionPolicy';
import {
  aisleExportsRoot,
  buildQuarantineFileName,
  ensureExportQuarantineDir,
  isAisleExportFinalName,
  isAisleExportTempName,
} from './exportArtifactPaths';
import {
  cleanupOutcomeLabel,
  emptyCleanupResult,
  type CleanupError,
  type CleanupResult,
} from './cleanupTypes';
import {
  assertSafeSandboxDeleteTarget,
  type SandboxRoots,
} from './safeSandboxPath';
import { exportStagingRoot } from './exportStaging';

export interface ExportArtifactReconcilerDeps {
  readonly captureRepo: CaptureRepository;
  readonly exportRepo: LocalCsvExportRepository;
  readonly attemptRepo: LocalExportAttemptRepository;
  readonly prepRepo?: ExportPrepRepository | null;
  readonly logger?: Logger | null;
  readonly ttls?: ArtifactRetentionTtls;
  readonly getRoots?: () => SandboxRoots;
}

export interface ReconcileLimits {
  readonly maxFiles: number;
  readonly maxSessions: number;
  readonly maxDurationMs: number;
  /** Heartbeat younger than this → treat attempt as active. */
  readonly activeAttemptGraceMs: number;
}

export const DEFAULT_RECONCILE_LIMITS: ReconcileLimits = {
  maxFiles: 80,
  maxSessions: 20,
  maxDurationMs: 8_000,
  activeAttemptGraceMs: 15 * 60 * 1000,
};

function defaultRoots(): SandboxRoots {
  return {
    documentDirectory: FileSystem.documentDirectory,
    cacheDirectory: FileSystem.cacheDirectory,
  };
}

async function safeDelete(
  uri: string,
  roots: SandboxRoots,
  errors: CleanupError[],
  artifactType: CleanupError['artifactType'],
  sessionRef?: string | null,
): Promise<boolean> {
  try {
    assertSafeSandboxDeleteTarget(uri, roots, {
      allowedPrefixes: ['export-staging/', 'aisle-exports/', 'export-quarantine/', 'dinamic-upload/'],
      allowSessionDirDelete: true,
    });
    await FileSystem.deleteAsync(uri, { idempotent: true });
    return true;
  } catch (error) {
    const code =
      error && typeof error === 'object' && 'code' in error
        ? String((error as { code: string }).code)
        : 'DELETE_FAILED';
    errors.push({
      code,
      artifactType,
      operation: 'delete',
      recoverable: true,
      sessionRef: sessionRef ?? null,
      message: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}

async function quarantineFile(
  uri: string,
  reasonCode: string,
  roots: SandboxRoots,
  errors: CleanupError[],
): Promise<boolean> {
  try {
    assertSafeSandboxDeleteTarget(uri, roots, {
      allowedPrefixes: ['aisle-exports/', 'export-staging/'],
    });
    const qDir = await ensureExportQuarantineDir();
    const base = uri.split('/').pop() ?? 'artifact';
    const dest = `${qDir}${buildQuarantineFileName({ originalName: base, reasonCode })}`;
    await FileSystem.moveAsync({ from: uri, to: dest });
    return true;
  } catch (error) {
    errors.push({
      code: 'QUARANTINE_FAILED',
      artifactType: 'unknown',
      operation: 'quarantine',
      recoverable: true,
      message: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}

export class ExportArtifactReconciler {
  private running = false;

  constructor(private readonly deps: ExportArtifactReconcilerDeps) {}

  /** Single-flight guard for bootstrap / concurrent cleanups. */
  async runBounded(limits: Partial<ReconcileLimits> = {}): Promise<CleanupResult> {
    if (this.running) {
      const started = Date.now();
      return {
        ...emptyCleanupResult(started),
        skippedActive: 1,
        errors: [
          {
            code: 'RECONCILE_ALREADY_RUNNING',
            artifactType: 'unknown',
            operation: 'reconcile',
            recoverable: true,
          },
        ],
      };
    }
    this.running = true;
    const started = Date.now();
    const cfg: ReconcileLimits = { ...DEFAULT_RECONCILE_LIMITS, ...limits };
    const errors: CleanupError[] = [];
    let scanned = 0;
    let deleted = 0;
    let quarantined = 0;
    let recovered = 0;
    let invalidated = 0;
    let skippedActive = 0;
    let bytesRecovered = 0;
    const roots = this.deps.getRoots?.() ?? defaultRoots();
    const ttls = this.deps.ttls ?? DEFAULT_ARTIFACT_RETENTION_TTLS;

    try {
      this.deps.logger?.info('storage.reconcile_started', {
        maxFiles: cfg.maxFiles,
        maxDurationMs: cfg.maxDurationMs,
      });

      // 1) Fail stale active attempts (temps become eligible for cleanup).
      //    Recover PUBLISHING with both finals present → complete durable export if possible.
      try {
        const stale = await this.deps.attemptRepo.failStaleActive(cfg.activeAttemptGraceMs);
        recovered += stale;
      } catch (error) {
        errors.push({
          code: 'FAIL_STALE_ATTEMPTS',
          artifactType: 'unknown',
          operation: 'fail_stale',
          recoverable: true,
          message: error instanceof Error ? error.message : String(error),
        });
      }
      try {
        const pub = await this.recoverPublishingAttempts(cfg, errors);
        recovered += pub.recovered;
        scanned += pub.scanned;
      } catch (error) {
        errors.push({
          code: 'RECOVER_PUBLISHING_FAILED',
          artifactType: 'zip_final',
          operation: 'recover_publishing',
          recoverable: true,
          message: error instanceof Error ? error.message : String(error),
        });
      }

      // 2) Invalidate READY jobs whose staging file is missing (bounded).
      if (this.deps.prepRepo) {
        try {
          const inv = await this.invalidateMissingReadyStaging(cfg, errors);
          invalidated += inv.invalidated;
          scanned += inv.scanned;
        } catch (error) {
          errors.push({
            code: 'INVALIDATE_READY_FAILED',
            artifactType: 'staging_ready',
            operation: 'invalidate',
            recoverable: true,
            message: error instanceof Error ? error.message : String(error),
          });
        }
      }

      if (Date.now() - started > cfg.maxDurationMs) {
        return this.finish(started, {
          scanned,
          deleted,
          quarantined,
          recovered,
          invalidated,
          skippedActive,
          failed: errors.length,
          errors,
          bytesRecovered,
        });
      }

      // 3) Clean aisle-exports temps without active attempts.
      const tempResult = await this.cleanupAisleExportTemps(cfg, roots, ttls, errors);
      scanned += tempResult.scanned;
      deleted += tempResult.deleted;
      skippedActive += tempResult.skippedActive;
      bytesRecovered += tempResult.bytesRecovered ?? 0;

      if (Date.now() - started > cfg.maxDurationMs || scanned >= cfg.maxFiles) {
        return this.finish(started, {
          scanned,
          deleted,
          quarantined,
          recovered,
          invalidated,
          skippedActive,
          failed: errors.length,
          errors,
          bytesRecovered,
        });
      }

      // 4) Orphan finals → quarantine only after authoritative reference miss.
      const orphanResult = await this.quarantineOrphanFinals(cfg, roots, ttls, errors);
      scanned += orphanResult.scanned;
      quarantined += orphanResult.quarantined;
      skippedActive += orphanResult.skippedActive;
      errors.push(...orphanResult.errors);

      // 5) Staging partial temps + orphan session dirs.
      const stagingTemps = await this.cleanupStagingTemps(cfg, roots, ttls, errors);
      scanned += stagingTemps.scanned;
      deleted += stagingTemps.deleted;
      quarantined += stagingTemps.quarantined;
      bytesRecovered += stagingTemps.bytesRecovered ?? 0;
      errors.push(...stagingTemps.errors);

      // 6) Quarantine TTL sweep.
      const qSweep = await this.sweepQuarantine(cfg, roots, ttls, errors);
      scanned += qSweep.scanned;
      deleted += qSweep.deleted;
      bytesRecovered += qSweep.bytesRecovered ?? 0;
      errors.push(...qSweep.errors);

      return this.finish(started, {
        scanned,
        deleted,
        quarantined,
        recovered,
        invalidated,
        skippedActive,
        failed: errors.length,
        errors,
        bytesRecovered,
      });
    } finally {
      this.running = false;
    }
  }

  private finish(
    started: number,
    partial: Omit<CleanupResult, 'durationMs'>,
  ): CleanupResult {
    const result: CleanupResult = {
      ...partial,
      durationMs: Date.now() - started,
    };
    const label = cleanupOutcomeLabel(result);
    this.deps.logger?.info(
      label === 'completed' ? 'storage.reconcile_completed' : 'storage.cleanup_partial',
      {
        scanned: result.scanned,
        deleted: result.deleted,
        quarantined: result.quarantined,
        recovered: result.recovered,
        invalidated: result.invalidated,
        skippedActive: result.skippedActive,
        failed: result.failed,
        durationMs: result.durationMs,
        bytesRecovered: result.bytesRecovered ?? 0,
      },
    );
    return result;
  }

  private async invalidateMissingReadyStaging(
    cfg: ReconcileLimits,
    errors: CleanupError[],
  ): Promise<{ scanned: number; invalidated: number }> {
    const prepRepo = this.deps.prepRepo!;
    const jobs = await prepRepo.listReadyJobs(Math.min(40, cfg.maxFiles));
    let scanned = 0;
    let invalidated = 0;
    for (const job of jobs) {
      if (scanned >= cfg.maxFiles) break;
      scanned += 1;
      if (!job.staging_uri) {
        try {
          await prepRepo.invalidateReady(job.capture_photo_id, 'STAGING_MISSING', 'staging_uri null');
          invalidated += 1;
          this.deps.logger?.info('storage.ready_invalidated', {
            code: 'STAGING_MISSING',
            sessionRef: job.capture_session_id.slice(0, 8),
          });
        } catch {
          errors.push({
            code: 'MARK_FAILED',
            artifactType: 'staging_ready',
            operation: 'invalidate',
            recoverable: true,
            sessionRef: job.capture_session_id.slice(0, 8),
          });
        }
        continue;
      }
      try {
        const info = await FileSystem.getInfoAsync(job.staging_uri, { size: true });
        const ok = info.exists && typeof info.size === 'number' && info.size > 0;
        if (!ok) {
          await prepRepo.invalidateReady(
            job.capture_photo_id,
            'STAGING_MISSING',
            'staging file missing or empty',
          );
          invalidated += 1;
          this.deps.logger?.info('storage.ready_invalidated', {
            code: 'STAGING_MISSING',
            sessionRef: job.capture_session_id.slice(0, 8),
          });
        }
      } catch {
        errors.push({
          code: 'STAGING_STAT_FAILED',
          artifactType: 'staging_ready',
          operation: 'stat',
          recoverable: true,
          sessionRef: job.capture_session_id.slice(0, 8),
        });
      }
    }
    return { scanned, invalidated };
  }

  private async activeTempUris(): Promise<Set<string>> {
    const active = await this.deps.attemptRepo.listActiveGlobal(100);
    const set = new Set<string>();
    for (const a of active) {
      if (isActiveExportAttemptState(a.state)) {
        if (a.tmp_csv_uri) set.add(a.tmp_csv_uri);
        if (a.tmp_zip_uri) set.add(a.tmp_zip_uri);
      }
    }
    return set;
  }

  /** Authoritative per-URI check — never use limited list as absence proof. */
  private async isFinalReferenced(uri: string): Promise<boolean> {
    if (await this.deps.exportRepo.isArtifactReferenced(uri)) return true;
    if (await this.deps.attemptRepo.isFinalUriReferencedByCompleteAttempt(uri)) return true;
    // Active/publishing attempts still own their finals/temps.
    const active = await this.deps.attemptRepo.listActiveGlobal(200);
    for (const a of active) {
      if (
        a.final_csv_uri === uri ||
        a.final_zip_uri === uri ||
        a.tmp_csv_uri === uri ||
        a.tmp_zip_uri === uri
      ) {
        return true;
      }
    }
    return false;
  }

  private async recoverPublishingAttempts(
    cfg: ReconcileLimits,
    errors: CleanupError[],
  ): Promise<{ scanned: number; recovered: number }> {
    let scanned = 0;
    let recovered = 0;
    const rows = await this.deps.attemptRepo.listPublishing(Math.min(40, cfg.maxFiles));
    for (const row of rows) {
      if (scanned >= cfg.maxFiles) break;
      scanned += 1;
      if (!row.final_csv_uri || !row.final_zip_uri) continue;
      try {
        const csvInfo = await FileSystem.getInfoAsync(row.final_csv_uri, { size: true });
        const zipInfo = await FileSystem.getInfoAsync(row.final_zip_uri, { size: true });
        const csvOk = csvInfo.exists && typeof csvInfo.size === 'number' && csvInfo.size > 0;
        const zipOk = zipInfo.exists && typeof zipInfo.size === 'number' && zipInfo.size > 0;
        if (!csvOk || !zipOk) continue;
        if (!row.content_fingerprint || !row.capture_session_id) continue;
        const existing = await this.deps.exportRepo.findBySessionAndFingerprint(
          row.capture_session_id,
          row.content_fingerprint,
        );
        if (existing) {
          await this.deps.attemptRepo.transitionState(row.id, 'COMPLETE', {
            completed_at: new Date().toISOString(),
          });
          recovered += 1;
          continue;
        }
        // Cannot invent full export row without schema fields — leave PUBLISHING for retry path.
        await this.deps.attemptRepo.heartbeat(row.id, new Date().toISOString());
      } catch (error) {
        errors.push({
          code: 'RECOVER_PUBLISHING_ROW_FAILED',
          artifactType: 'zip_final',
          operation: 'recover_publishing',
          recoverable: true,
          sessionRef: row.capture_session_id.slice(0, 8),
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
    return { scanned, recovered };
  }

  private async cleanupAisleExportTemps(
    cfg: ReconcileLimits,
    roots: SandboxRoots,
    ttls: ArtifactRetentionTtls,
    errors: CleanupError[],
  ): Promise<CleanupResult> {
    const started = Date.now();
    let scanned = 0;
    let deleted = 0;
    let skippedActive = 0;
    let bytesRecovered = 0;
    let dir: string;
    try {
      dir = aisleExportsRoot();
    } catch (error) {
      errors.push({
        code: 'AISLE_EXPORTS_ROOT_UNAVAILABLE',
        artifactType: 'zip_temp',
        operation: 'scan',
        recoverable: true,
        message: error instanceof Error ? error.message : String(error),
      });
      return { ...emptyCleanupResult(started), failed: 1, errors: [...errors] };
    }
    let names: string[] = [];
    try {
      const info = await FileSystem.getInfoAsync(dir);
      if (!info.exists) return emptyCleanupResult(started);
      names = await FileSystem.readDirectoryAsync(dir);
    } catch (error) {
      errors.push({
        code: 'AISLE_EXPORTS_READ_FAILED',
        artifactType: 'zip_temp',
        operation: 'scan',
        recoverable: true,
        message: error instanceof Error ? error.message : String(error),
      });
      return {
        scanned: 0,
        deleted: 0,
        quarantined: 0,
        recovered: 0,
        invalidated: 0,
        skippedActive: 0,
        failed: 1,
        errors: [
          {
            code: 'AISLE_EXPORTS_READ_FAILED',
            artifactType: 'zip_temp',
            operation: 'scan',
            recoverable: true,
            message: error instanceof Error ? error.message : String(error),
          },
        ],
        durationMs: Date.now() - started,
      };
    }

    const activeTemps = await this.activeTempUris();
    const now = Date.now();

    for (const name of names) {
      if (scanned >= cfg.maxFiles || Date.now() - started > cfg.maxDurationMs) break;
      if (!isAisleExportTempName(name)) continue;
      scanned += 1;
      const uri = `${dir}${name}`;
      if (activeTemps.has(uri)) {
        skippedActive += 1;
        continue;
      }
      let ageMs = ttls.zipTempMs + 1;
      let size = 0;
      try {
        const meta = await FileSystem.getInfoAsync(uri, { size: true });
        if (meta.exists && 'modificationTime' in meta && typeof meta.modificationTime === 'number') {
          ageMs = now - meta.modificationTime * 1000;
        }
        if (meta.exists && typeof meta.size === 'number') size = meta.size;
      } catch (error) {
        errors.push({
          code: 'TEMP_STAT_FAILED',
          artifactType: 'zip_temp',
          operation: 'stat',
          recoverable: true,
          message: error instanceof Error ? error.message : String(error),
        });
        continue;
      }
      const decision = decideArtifactRetention({
        artifactClass: name.endsWith('.csv') ? 'csv_temp' : 'zip_temp',
        ageMs,
        ttls,
        hasActiveLeaseOrAttempt: false,
      });
      if (decision.action !== 'cleanup_safe') {
        skippedActive += 1;
        continue;
      }
      const ok = await safeDelete(uri, roots, errors, name.endsWith('.csv') ? 'csv_temp' : 'zip_temp');
      if (ok) {
        deleted += 1;
        bytesRecovered += size;
      }
    }

    return {
      scanned,
      deleted,
      quarantined: 0,
      recovered: 0,
      invalidated: 0,
      skippedActive,
      failed: 0,
      errors: [],
      durationMs: Date.now() - started,
      bytesRecovered,
    };
  }

  private async quarantineOrphanFinals(
    cfg: ReconcileLimits,
    roots: SandboxRoots,
    ttls: ArtifactRetentionTtls,
    _errors: CleanupError[],
  ): Promise<CleanupResult> {
    const started = Date.now();
    let scanned = 0;
    let quarantined = 0;
    let skippedActive = 0;
    const localErrors: CleanupError[] = [];
    let dir: string;
    try {
      dir = aisleExportsRoot();
    } catch (error) {
      localErrors.push({
        code: 'AISLE_EXPORTS_ROOT_UNAVAILABLE',
        artifactType: 'zip_final',
        operation: 'scan',
        recoverable: true,
        message: error instanceof Error ? error.message : String(error),
      });
      return { ...emptyCleanupResult(started), failed: 1, errors: localErrors };
    }
    let names: string[] = [];
    try {
      const info = await FileSystem.getInfoAsync(dir);
      if (!info.exists) return emptyCleanupResult(started);
      names = await FileSystem.readDirectoryAsync(dir);
    } catch (error) {
      localErrors.push({
        code: 'AISLE_EXPORTS_READ_FAILED',
        artifactType: 'zip_final',
        operation: 'scan',
        recoverable: true,
        message: error instanceof Error ? error.message : String(error),
      });
      return {
        ...emptyCleanupResult(started),
        failed: 1,
        errors: localErrors,
      };
    }

    const now = Date.now();
    for (const name of names) {
      if (scanned >= cfg.maxFiles || Date.now() - started > cfg.maxDurationMs) break;
      if (!isAisleExportFinalName(name)) continue;
      scanned += 1;
      const uri = `${dir}${name}`;

      let referenced = false;
      try {
        referenced = await this.isFinalReferenced(uri);
      } catch (error) {
        localErrors.push({
          code: 'REFERENCE_LOOKUP_FAILED',
          artifactType: name.endsWith('.zip') ? 'zip_final' : 'csv_final',
          operation: 'reference_check',
          recoverable: true,
          message: error instanceof Error ? error.message : String(error),
        });
        skippedActive += 1;
        continue;
      }
      if (referenced) {
        skippedActive += 1;
        continue;
      }

      let ageMs = 0;
      try {
        const meta = await FileSystem.getInfoAsync(uri);
        if (meta.exists && 'modificationTime' in meta && typeof meta.modificationTime === 'number') {
          ageMs = now - meta.modificationTime * 1000;
        }
      } catch {
        ageMs = ttls.orphanFinalMs + 1;
      }

      const decision = decideArtifactRetention({
        artifactClass: 'orphan_final',
        ageMs,
        ttls,
        referencedByCompleteExport: false,
      });
      if (decision.action !== 'quarantine') {
        skippedActive += 1;
        continue;
      }
      this.deps.logger?.info('storage.orphan_detected', {
        artifact: name.endsWith('.zip') ? 'zip_final' : 'csv_final',
        reason: decision.reason,
      });
      const ok = await quarantineFile(uri, decision.reason, roots, localErrors);
      if (ok) {
        quarantined += 1;
        this.deps.logger?.info('storage.artifact_quarantined', {
          reason: decision.reason,
          artifact: name.endsWith('.zip') ? 'zip_final' : 'csv_final',
        });
      }
    }

    return {
      scanned,
      deleted: 0,
      quarantined,
      recovered: 0,
      invalidated: 0,
      skippedActive,
      failed: localErrors.length,
      errors: localErrors,
      durationMs: Date.now() - started,
    };
  }

  private async cleanupStagingTemps(
    cfg: ReconcileLimits,
    roots: SandboxRoots,
    ttls: ArtifactRetentionTtls,
    _errors: CleanupError[],
  ): Promise<CleanupResult> {
    const started = Date.now();
    let scanned = 0;
    let deleted = 0;
    let quarantined = 0;
    let bytesRecovered = 0;
    const localErrors: CleanupError[] = [];
    let root: string;
    try {
      root = exportStagingRoot();
    } catch {
      return emptyCleanupResult(started);
    }
    let sessions: string[] = [];
    try {
      const info = await FileSystem.getInfoAsync(root);
      if (!info.exists) return emptyCleanupResult(started);
      sessions = await FileSystem.readDirectoryAsync(root);
    } catch (error) {
      localErrors.push({
        code: 'STAGING_ROOT_READ_FAILED',
        artifactType: 'staging_temp',
        operation: 'scan',
        recoverable: true,
        message: error instanceof Error ? error.message : String(error),
      });
      return { ...emptyCleanupResult(started), failed: 1, errors: localErrors };
    }

    const now = Date.now();
    let sessionCount = 0;
    for (const session of sessions) {
      if (sessionCount >= cfg.maxSessions) break;
      sessionCount += 1;

      // Orphan session dir: no capture_sessions row → quarantine/cleanup staging (not flag-based).
      let sessionExists = true;
      try {
        const row = await this.deps.captureRepo.getSession(session);
        sessionExists = Boolean(row);
      } catch {
        sessionExists = true; // DB unavailable — never delete on assumption
      }

      const photosDir = `${root}${session}/photos/`;
      let entries: string[] = [];
      try {
        entries = await FileSystem.readDirectoryAsync(photosDir);
      } catch {
        continue;
      }

      if (!sessionExists) {
        for (const name of entries) {
          if (scanned >= cfg.maxFiles || Date.now() - started > cfg.maxDurationMs) break;
          scanned += 1;
          const uri = `${photosDir}${name}`;
          if (name.includes('.tmp')) {
            const ok = await safeDelete(uri, roots, localErrors, 'staging_temp', session.slice(0, 8));
            if (ok) deleted += 1;
          } else {
            const ok = await quarantineFile(uri, 'session_missing', roots, localErrors);
            if (ok) quarantined += 1;
          }
        }
        continue;
      }

      for (const name of entries) {
        if (scanned >= cfg.maxFiles || Date.now() - started > cfg.maxDurationMs) {
          return {
            scanned,
            deleted,
            quarantined,
            recovered: 0,
            invalidated: 0,
            skippedActive: 0,
            failed: localErrors.length,
            errors: localErrors,
            durationMs: Date.now() - started,
            bytesRecovered,
          };
        }
        if (!name.includes('.tmp')) continue;
        scanned += 1;
        const uri = `${photosDir}${name}`;
        let ageMs = ttls.stagingPartialMs + 1;
        let size = 0;
        try {
          const meta = await FileSystem.getInfoAsync(uri, { size: true });
          if (meta.exists && 'modificationTime' in meta && typeof meta.modificationTime === 'number') {
            ageMs = now - meta.modificationTime * 1000;
          }
          if (meta.exists && typeof meta.size === 'number') size = meta.size;
        } catch {
          // treat as expired for partial temps only
        }
        const decision = decideArtifactRetention({
          artifactClass: 'staging_partial',
          ageMs,
          ttls,
        });
        if (decision.action !== 'cleanup_safe') continue;
        const ok = await safeDelete(uri, roots, localErrors, 'staging_temp', session.slice(0, 8));
        if (ok) {
          deleted += 1;
          bytesRecovered += size;
        }
      }
    }

    return {
      scanned,
      deleted,
      quarantined,
      recovered: 0,
      invalidated: 0,
      skippedActive: 0,
      failed: localErrors.length,
      errors: localErrors,
      durationMs: Date.now() - started,
      bytesRecovered,
    };
  }

  private async sweepQuarantine(
    cfg: ReconcileLimits,
    roots: SandboxRoots,
    ttls: ArtifactRetentionTtls,
    _errors: CleanupError[],
  ): Promise<CleanupResult> {
    const started = Date.now();
    let scanned = 0;
    let deleted = 0;
    let bytesRecovered = 0;
    const localErrors: CleanupError[] = [];
    let dir: string;
    try {
      dir = `${roots.documentDirectory ?? ''}export-quarantine/`;
      if (!roots.documentDirectory) return emptyCleanupResult(started);
    } catch {
      return emptyCleanupResult(started);
    }
    let names: string[] = [];
    try {
      const info = await FileSystem.getInfoAsync(dir);
      if (!info.exists) return emptyCleanupResult(started);
      names = await FileSystem.readDirectoryAsync(dir);
    } catch (error) {
      localErrors.push({
        code: 'QUARANTINE_READ_FAILED',
        artifactType: 'quarantine',
        operation: 'scan',
        recoverable: true,
        message: error instanceof Error ? error.message : String(error),
      });
      return { ...emptyCleanupResult(started), failed: 1, errors: localErrors };
    }

    const now = Date.now();
    for (const name of names) {
      if (scanned >= cfg.maxFiles || Date.now() - started > cfg.maxDurationMs) break;
      scanned += 1;
      const uri = `${dir}${name}`;
      let ageMs = 0;
      let size = 0;
      try {
        const meta = await FileSystem.getInfoAsync(uri, { size: true });
        if (meta.exists && 'modificationTime' in meta && typeof meta.modificationTime === 'number') {
          ageMs = now - meta.modificationTime * 1000;
        }
        if (meta.exists && typeof meta.size === 'number') size = meta.size;
      } catch (error) {
        localErrors.push({
          code: 'QUARANTINE_STAT_FAILED',
          artifactType: 'quarantine',
          operation: 'stat',
          recoverable: true,
          message: error instanceof Error ? error.message : String(error),
        });
        continue;
      }
      const decision = decideArtifactRetention({
        artifactClass: 'quarantine',
        ageMs,
        ttls,
      });
      if (decision.action !== 'cleanup_safe') continue;
      const ok = await safeDelete(uri, roots, localErrors, 'quarantine');
      if (ok) {
        deleted += 1;
        bytesRecovered += size;
      }
    }

    return {
      scanned,
      deleted,
      quarantined: 0,
      recovered: 0,
      invalidated: 0,
      skippedActive: 0,
      failed: localErrors.length,
      errors: localErrors,
      durationMs: Date.now() - started,
      bytesRecovered,
    };
  }
}
