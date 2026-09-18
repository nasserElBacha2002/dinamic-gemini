/**
 * Retention / ownership policy for export artifacts (Phase 6).
 * Decisions combine persisted state + lease + TTL — never age alone.
 */

export type ArtifactClass =
  | 'original_mediastore'
  | 'staging_ready'
  | 'staging_partial'
  | 'zip_temp'
  | 'csv_temp'
  | 'zip_final'
  | 'csv_final'
  | 'orphan_final'
  | 'quarantine';

export type RetentionAction =
  | 'keep'
  | 'cleanup_safe'
  | 'quarantine'
  | 'purge_on_session_delete'
  | 'never_auto_delete';

/** Configurable TTLs (ms). */
export interface ArtifactRetentionTtls {
  readonly stagingPartialMs: number;
  readonly zipTempMs: number;
  readonly csvTempMs: number;
  readonly quarantineMs: number;
  readonly orphanFinalMs: number;
  readonly transformTempMs: number;
}

export const DEFAULT_ARTIFACT_RETENTION_TTLS: ArtifactRetentionTtls = {
  stagingPartialMs: 24 * 60 * 60 * 1000,
  zipTempMs: 6 * 60 * 60 * 1000,
  csvTempMs: 6 * 60 * 60 * 1000,
  quarantineMs: 7 * 24 * 60 * 60 * 1000,
  orphanFinalMs: 48 * 60 * 60 * 1000,
  transformTempMs: 48 * 60 * 60 * 1000,
};

export type ExportAttemptState =
  | 'CREATED'
  | 'WRITING'
  | 'VALIDATING'
  | 'PUBLISHING'
  | 'COMPLETE'
  | 'FAILED'
  | 'CANCELLED';

const ACTIVE_ATTEMPT_STATES: ReadonlySet<ExportAttemptState> = new Set([
  'CREATED',
  'WRITING',
  'VALIDATING',
  'PUBLISHING',
]);

export function isActiveExportAttemptState(state: string): boolean {
  return ACTIVE_ATTEMPT_STATES.has(state as ExportAttemptState);
}

export interface RetentionDecisionInput {
  readonly artifactClass: ArtifactClass;
  readonly ageMs: number;
  readonly ttls?: ArtifactRetentionTtls;
  /** Job / attempt still claimed or heartbeat fresh. */
  readonly hasActiveLeaseOrAttempt?: boolean;
  /** Referenced by COMPLETE local_csv_exports row. */
  readonly referencedByCompleteExport?: boolean;
  /** Session still present in SQLite. */
  readonly sessionExists?: boolean;
  /** Explicit session purge requested. */
  readonly sessionPurgeRequested?: boolean;
  /** Prep job status when known. */
  readonly prepJobStatus?: string | null;
  /** mobileExportPrepQueue flag — never auto-delete staging solely because flag is off. */
  readonly exportPrepFlagEnabled?: boolean | null;
}

export interface RetentionDecision {
  readonly action: RetentionAction;
  readonly reason: string;
}

/**
 * Decide retention for one artifact. Prefer keep / quarantine over delete.
 */
export function decideArtifactRetention(input: RetentionDecisionInput): RetentionDecision {
  const ttls = input.ttls ?? DEFAULT_ARTIFACT_RETENTION_TTLS;

  if (input.artifactClass === 'original_mediastore') {
    return { action: 'never_auto_delete', reason: 'mediastore_owned' };
  }

  if (input.sessionPurgeRequested) {
    return { action: 'purge_on_session_delete', reason: 'session_purge' };
  }

  if (input.hasActiveLeaseOrAttempt) {
    return { action: 'keep', reason: 'active_lease_or_attempt' };
  }

  if (input.artifactClass === 'staging_ready') {
    if (input.prepJobStatus === 'EXCLUDED') {
      if (input.referencedByCompleteExport) {
        return { action: 'keep', reason: 'referenced_by_export' };
      }
      return { action: 'cleanup_safe', reason: 'excluded_unreferenced' };
    }
    // Flag off must not reinterpret READY staging as orphan.
    return { action: 'keep', reason: 'staging_ready_required' };
  }

  if (input.artifactClass === 'staging_partial') {
    if (input.ageMs >= ttls.stagingPartialMs) {
      return { action: 'cleanup_safe', reason: 'staging_partial_ttl' };
    }
    return { action: 'keep', reason: 'staging_partial_fresh' };
  }

  if (input.artifactClass === 'zip_temp' || input.artifactClass === 'csv_temp') {
    const ttl = input.artifactClass === 'zip_temp' ? ttls.zipTempMs : ttls.csvTempMs;
    if (input.ageMs >= ttl) {
      return { action: 'cleanup_safe', reason: 'temp_ttl' };
    }
    return { action: 'keep', reason: 'temp_fresh' };
  }

  if (input.artifactClass === 'zip_final' || input.artifactClass === 'csv_final') {
    if (input.referencedByCompleteExport) {
      return { action: 'keep', reason: 'complete_export' };
    }
    if (input.sessionExists === false && input.ageMs >= ttls.orphanFinalMs) {
      return { action: 'quarantine', reason: 'final_without_session' };
    }
    if (input.referencedByCompleteExport === false && input.ageMs >= ttls.orphanFinalMs) {
      return { action: 'quarantine', reason: 'final_without_record' };
    }
    return { action: 'keep', reason: 'final_pending_reconcile' };
  }

  if (input.artifactClass === 'orphan_final') {
    if (input.ageMs >= ttls.orphanFinalMs) {
      return { action: 'quarantine', reason: 'orphan_final_ttl' };
    }
    return { action: 'keep', reason: 'orphan_final_fresh' };
  }

  if (input.artifactClass === 'quarantine') {
    if (input.ageMs >= ttls.quarantineMs) {
      return { action: 'cleanup_safe', reason: 'quarantine_ttl' };
    }
    return { action: 'keep', reason: 'quarantine_fresh' };
  }

  return { action: 'keep', reason: 'default_keep' };
}

export type StorageSpaceLevel =
  | 'OK'
  | 'LOW_SPACE_WARNING'
  | 'INSUFFICIENT_FOR_OPERATION'
  | 'UNKNOWN';

export type StorageFailure =
  | 'STORAGE_STATUS_UNKNOWN'
  | 'STORAGE_LOW'
  | 'STORAGE_INSUFFICIENT_FOR_STAGING'
  | 'STORAGE_INSUFFICIENT_FOR_EXPORT'
  | 'STORAGE_WRITE_FAILED'
  | 'STORAGE_PERMISSION_DENIED';

export interface StorageSpaceAssessment {
  readonly level: StorageSpaceLevel;
  readonly freeBytes: number | null;
  readonly requiredBytes: number;
  readonly failure?: StorageFailure;
}

/**
 * Estimate need = pending + zip overhead + temps + operating margin.
 */
export function assessStorageSpace(input: {
  readonly freeBytes: number | null;
  readonly estimatedPayloadBytes: number;
  readonly zipOverheadFactor?: number;
  readonly tempMultiplier?: number;
  readonly operatingMarginBytes?: number;
  readonly lowSpaceWarnBytes?: number;
}): StorageSpaceAssessment {
  const overhead = input.zipOverheadFactor ?? 1.15;
  const tempMul = input.tempMultiplier ?? 2;
  const margin = input.operatingMarginBytes ?? 64 * 1024 * 1024;
  const warn = input.lowSpaceWarnBytes ?? 500 * 1024 * 1024;
  const required = Math.ceil(input.estimatedPayloadBytes * overhead * tempMul) + margin;

  if (input.freeBytes == null || !Number.isFinite(input.freeBytes)) {
    return {
      level: 'UNKNOWN',
      freeBytes: null,
      requiredBytes: required,
      failure: 'STORAGE_STATUS_UNKNOWN',
    };
  }

  if (input.freeBytes < required) {
    return {
      level: 'INSUFFICIENT_FOR_OPERATION',
      freeBytes: input.freeBytes,
      requiredBytes: required,
      failure: 'STORAGE_INSUFFICIENT_FOR_EXPORT',
    };
  }

  if (input.freeBytes < warn) {
    return {
      level: 'LOW_SPACE_WARNING',
      freeBytes: input.freeBytes,
      requiredBytes: required,
      failure: 'STORAGE_LOW',
    };
  }

  return { level: 'OK', freeBytes: input.freeBytes, requiredBytes: required };
}
