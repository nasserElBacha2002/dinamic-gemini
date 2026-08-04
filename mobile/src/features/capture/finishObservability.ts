import { emitObservability } from '../../observability';
import type { ObservabilityReporter } from '../../observability';
import type { ObservabilityAttributeValue } from '../../observability/types';
import type { CapturePhotoRow, CaptureSessionRow } from '../../database/schema/captureSchema';

export type CaptureFinishStage =
  | 'checking_media'
  | 'validating'
  | 'closing'
  | 'preparing_review'
  | null;

export const FINISH_STAGE_LABELS: Record<Exclude<CaptureFinishStage, null>, string> = {
  checking_media: 'Verificando últimas fotos…',
  validating: 'Validando fotos…',
  closing: 'Cerrando captura…',
  preparing_review: 'Preparando revisión…',
};

export interface FinishPhotoCounts {
  readonly photo_count: number;
  readonly stable_count: number;
  readonly pending_count: number;
  readonly excluded_count: number;
  readonly error_count: number;
}

export function countFinishPhotos(photos: readonly CapturePhotoRow[]): FinishPhotoCounts {
  let stable = 0;
  let pending = 0;
  let excluded = 0;
  let errors = 0;
  for (const p of photos) {
    if (p.status === 'stable') stable += 1;
    else if (p.status === 'detected' || p.status === 'waiting_stability') pending += 1;
    else if (p.status === 'excluded' || p.status === 'rejected') excluded += 1;
    else if (p.status === 'unstable' || p.status === 'undecodable') errors += 1;
  }
  return {
    photo_count: photos.length,
    stable_count: stable,
    pending_count: pending,
    excluded_count: excluded,
    error_count: errors,
  };
}

export function finishBaseAttributes(input: {
  readonly session: CaptureSessionRow;
  readonly photos: readonly CapturePhotoRow[];
  readonly statusBefore?: string | null;
  readonly statusAfter?: string | null;
  readonly activeValidationCount?: number;
  readonly newMediaCandidateCount?: number | null;
  readonly sqliteBusyCount?: number;
  readonly errorCode?: string | null;
  readonly errorStage?: string | null;
  readonly appState?: string | null;
  readonly foregroundServiceActive?: boolean | null;
  readonly finishStage?: CaptureFinishStage;
  readonly skippedFullRescan?: boolean | null;
}): Record<string, ObservabilityAttributeValue> {
  const counts = countFinishPhotos(input.photos);
  return {
    inventory_id: input.session.inventory_id,
    aisle_id: input.session.aisle_id,
    status_before: input.statusBefore ?? null,
    status_after: input.statusAfter ?? null,
    ...counts,
    active_validation_count: input.activeValidationCount ?? null,
    new_media_candidate_count: input.newMediaCandidateCount ?? null,
    sqlite_busy_count: input.sqliteBusyCount ?? 0,
    error_code: input.errorCode ?? null,
    error_stage: input.errorStage ?? null,
    app_state: input.appState ?? null,
    foreground_service_active: input.foregroundServiceActive ?? null,
    finish_stage: input.finishStage ?? null,
    skipped_full_rescan: input.skippedFullRescan ?? null,
  };
}

export function emitFinishEvent(
  reporter: ObservabilityReporter | null | undefined,
  input: {
    readonly name: string;
    readonly sessionId: string;
    readonly durationMs?: number;
    readonly attributes: Readonly<Record<string, ObservabilityAttributeValue>>;
  },
): void {
  emitObservability(reporter, {
    name: input.name,
    sessionId: input.sessionId,
    durationMs: input.durationMs,
    attributes: input.attributes,
  });
}

export function stageDurationMs(startedAt: number, nowMs: () => number = Date.now): number {
  return Math.max(0, Math.round(nowMs() - startedAt));
}
