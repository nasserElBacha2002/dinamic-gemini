/** Local + server readiness types for authoritative aisle finalization (Phase 6). */

export type AuthoritativeAisleReadinessStatus = 'READY' | 'NOT_READY' | 'BLOCKED';

export type AuthoritativeReadinessReason =
  | 'PENDING_LOCAL_SCAN'
  | 'PENDING_LOCAL_REVIEW'
  | 'PENDING_CONFIRMATION'
  | 'PENDING_UPLOAD'
  | 'PENDING_AUTHORITATIVE_SYNC'
  | 'PENDING_FINAL_APPLY'
  | 'AUTHORITATIVE_CONFLICT'
  | 'AUTHORITATIVE_REJECTED'
  | 'AUTHORITATIVE_FAILED_TERMINAL'
  | 'PHOTO_NOT_DECIDED'
  | 'ASSET_MISSING'
  | 'POSITION_MISSING'
  | 'DUPLICATE_CURRENT_POSITION'
  | 'SESSION_INCONSISTENT'
  | 'FEATURE_DISABLED'
  | 'AISLE_ALREADY_FINALIZED'
  | 'NETWORK_OFFLINE';

export interface AuthoritativeAisleReadiness {
  readonly status: AuthoritativeAisleReadinessStatus;
  readonly totalImages: number;
  readonly appliedImages: number;
  readonly excludedImages: number;
  readonly pendingImages: number;
  readonly conflictedImages: number;
  readonly failedImages: number;
  readonly reasons: readonly AuthoritativeReadinessReason[];
  readonly uniqueCodes: number;
  readonly totalQuantity: number;
  readonly canApply: boolean;
  readonly canFinalize: boolean;
}

export interface AuthoritativeAisleReadinessApiDto {
  readonly status: string;
  readonly total_images: number;
  readonly applied_images: number;
  readonly excluded_images: number;
  readonly pending_images: number;
  readonly conflicted_images: number;
  readonly failed_images: number;
  readonly reasons: readonly string[];
  readonly unique_codes?: number;
  readonly total_quantity?: number;
  readonly can_apply?: boolean;
  readonly can_finalize?: boolean;
}

export function mapAuthoritativeReadinessDto(
  dto: AuthoritativeAisleReadinessApiDto,
): AuthoritativeAisleReadiness {
  const status =
    dto.status === 'READY' || dto.status === 'BLOCKED' || dto.status === 'NOT_READY'
      ? dto.status
      : 'NOT_READY';
  return {
    status,
    totalImages: dto.total_images,
    appliedImages: dto.applied_images,
    excludedImages: dto.excluded_images,
    pendingImages: dto.pending_images,
    conflictedImages: dto.conflicted_images,
    failedImages: dto.failed_images,
    reasons: dto.reasons as AuthoritativeReadinessReason[],
    uniqueCodes: dto.unique_codes ?? 0,
    totalQuantity: dto.total_quantity ?? 0,
    canApply: dto.can_apply ?? status === 'READY',
    canFinalize: dto.can_finalize ?? status === 'READY',
  };
}

/** Evaluate local SQLite readiness (fail-closed; server remains authority). */
export function evaluateLocalAuthoritativeAisleReadiness(input: {
  readonly photos: readonly {
    readonly id: string;
    readonly upload_status: string;
    readonly backend_asset_id: string | null;
  }[];
  readonly confirmed: readonly {
    readonly capture_photo_id: string;
    readonly sync_status: string;
    readonly applied_at: string | null;
  }[];
  readonly enabled: boolean;
}): AuthoritativeAisleReadiness {
  if (!input.enabled) {
    return emptyReadiness('BLOCKED', ['FEATURE_DISABLED']);
  }
  const confirmedByPhoto = new Map(input.confirmed.map((c) => [c.capture_photo_id, c]));
  let applied = 0;
  let excluded = 0;
  let pending = 0;
  let conflicted = 0;
  let failed = 0;
  const reasons: AuthoritativeReadinessReason[] = [];

  for (const photo of input.photos) {
    if (photo.upload_status === 'excluded' || photo.upload_status === 'remote_deleted') {
      excluded += 1;
      continue;
    }
    if (
      photo.upload_status !== 'uploaded' ||
      !photo.backend_asset_id
    ) {
      pending += 1;
      reasons.push('PENDING_UPLOAD');
      continue;
    }
    const row = confirmedByPhoto.get(photo.id);
    if (!row) {
      pending += 1;
      reasons.push('PENDING_CONFIRMATION');
      continue;
    }
    if (row.sync_status === 'CONFLICT') {
      conflicted += 1;
      reasons.push('AUTHORITATIVE_CONFLICT');
      continue;
    }
    if (row.sync_status === 'REJECTED') {
      failed += 1;
      reasons.push('AUTHORITATIVE_REJECTED');
      continue;
    }
    if (row.sync_status === 'FAILED_TERMINAL') {
      failed += 1;
      reasons.push('AUTHORITATIVE_FAILED_TERMINAL');
      continue;
    }
    if (row.sync_status !== 'SYNCED') {
      pending += 1;
      reasons.push('PENDING_AUTHORITATIVE_SYNC');
      continue;
    }
    if (!row.applied_at) {
      pending += 1;
      reasons.push('PENDING_FINAL_APPLY');
      continue;
    }
    applied += 1;
  }

  const total = input.photos.length;
  const uniqReasons = [...new Set(reasons)];
  let status: AuthoritativeAisleReadinessStatus = 'NOT_READY';
  if (conflicted > 0) status = 'BLOCKED';
  else if (total === 0) {
    status = 'NOT_READY';
    uniqReasons.push('ASSET_MISSING');
  } else if (pending === 0 && failed === 0 && applied + excluded === total) {
    status = 'READY';
  }

  return {
    status,
    totalImages: total,
    appliedImages: applied,
    excludedImages: excluded,
    pendingImages: pending,
    conflictedImages: conflicted,
    failedImages: failed,
    reasons: status === 'READY' ? [] : uniqReasons,
    uniqueCodes: 0,
    totalQuantity: 0,
    canApply: status === 'READY' || (pending === 0 && conflicted === 0 && failed === 0),
    canFinalize: status === 'READY',
  };
}

function emptyReadiness(
  status: AuthoritativeAisleReadinessStatus,
  reasons: AuthoritativeReadinessReason[],
): AuthoritativeAisleReadiness {
  return {
    status,
    totalImages: 0,
    appliedImages: 0,
    excludedImages: 0,
    pendingImages: 0,
    conflictedImages: 0,
    failedImages: 0,
    reasons,
    uniqueCodes: 0,
    totalQuantity: 0,
    canApply: false,
    canFinalize: false,
  };
}
