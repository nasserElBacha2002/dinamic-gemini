/**
 * Structured cleanup / reconcile results (Phase 6).
 */

export type CleanupArtifactType =
  | 'staging_temp'
  | 'staging_ready'
  | 'zip_temp'
  | 'csv_temp'
  | 'zip_final'
  | 'csv_final'
  | 'quarantine'
  | 'transform_temp'
  | 'unknown';

export interface CleanupError {
  readonly code: string;
  readonly artifactType: CleanupArtifactType;
  readonly operation: string;
  readonly recoverable: boolean;
  /** Anonymized session token when known (never full path). */
  readonly sessionRef?: string | null;
  readonly message?: string;
}

export interface CleanupResult {
  readonly scanned: number;
  readonly deleted: number;
  readonly quarantined: number;
  readonly recovered: number;
  readonly invalidated: number;
  readonly skippedActive: number;
  readonly failed: number;
  readonly errors: readonly CleanupError[];
  readonly durationMs: number;
  readonly bytesRecovered?: number;
  readonly continuationToken?: string | null;
}

export function emptyCleanupResult(startedAtMs: number): CleanupResult {
  return {
    scanned: 0,
    deleted: 0,
    quarantined: 0,
    recovered: 0,
    invalidated: 0,
    skippedActive: 0,
    failed: 0,
    errors: [],
    durationMs: Math.max(0, Date.now() - startedAtMs),
  };
}

export function mergeCleanupResults(parts: readonly CleanupResult[]): CleanupResult {
  const errors: CleanupError[] = [];
  let scanned = 0;
  let deleted = 0;
  let quarantined = 0;
  let recovered = 0;
  let invalidated = 0;
  let skippedActive = 0;
  let failed = 0;
  let bytesRecovered = 0;
  let durationMs = 0;
  for (const p of parts) {
    scanned += p.scanned;
    deleted += p.deleted;
    quarantined += p.quarantined;
    recovered += p.recovered;
    invalidated += p.invalidated;
    skippedActive += p.skippedActive;
    failed += p.failed;
    bytesRecovered += p.bytesRecovered ?? 0;
    durationMs += p.durationMs;
    errors.push(...p.errors);
  }
  return {
    scanned,
    deleted,
    quarantined,
    recovered,
    invalidated,
    skippedActive,
    failed,
    errors,
    durationMs,
    bytesRecovered,
  };
}

export function cleanupOutcomeLabel(result: CleanupResult): 'completed' | 'partial' | 'failed' {
  if (result.failed > 0 && result.deleted === 0 && result.quarantined === 0) {
    return 'failed';
  }
  if (result.failed > 0) return 'partial';
  return 'completed';
}
