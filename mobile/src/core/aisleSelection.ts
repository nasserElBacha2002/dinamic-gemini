/**
 * Runtime-safe aisle selection rules for mobile capture.
 * Do not trust TypeScript shapes alone — normalize wire JSON first.
 */

export type AisleBlockReason =
  | 'inactive'
  | 'processing'
  | 'capture_in_progress'
  | 'not_authorized'
  | 'invalid_data'
  | null;

export interface AisleSelectionResult {
  readonly selectable: boolean;
  readonly reason: AisleBlockReason;
}

export interface AisleSelectionInput {
  readonly id?: unknown;
  readonly code?: unknown;
  readonly status?: unknown;
  readonly is_active?: unknown;
  readonly isActive?: unknown;
  readonly latest_job?: unknown;
  readonly latestJob?: unknown;
}

export interface LocalCaptureHint {
  /** True when this device already has an exclusive local capture for the aisle. */
  readonly exclusiveCaptureOpen?: boolean;
  /** True when the open exclusive capture belongs to a *different* aisle. */
  readonly exclusiveCaptureOnOtherAisle?: boolean;
}

const ACTIVE_JOB_STATUSES = new Set([
  'queued',
  'starting',
  'pending',
  'running',
  'processing',
  'cancel_requested',
]);

const AISLE_PROCESSING_STATUSES = new Set(['queued', 'processing']);

export function normalizeStatus(raw: unknown): string {
  if (typeof raw !== 'string') {
    return '';
  }
  return raw.trim().toLowerCase().replace(/\s+/g, '_');
}

/**
 * Soft-active: missing / null / undefined → active (compat with older payloads).
 * Only explicit false / 0 / "false" / "0" → inactive.
 */
export function normalizeIsActive(raw: unknown): boolean {
  if (raw === false || raw === 0 || raw === '0' || raw === 'false' || raw === 'False') {
    return false;
  }
  return true;
}

function readLatestJobStatus(aisle: AisleSelectionInput): string {
  const job = (aisle.latest_job ?? aisle.latestJob) as { status?: unknown } | null | undefined;
  if (!job || typeof job !== 'object') {
    return '';
  }
  return normalizeStatus(job.status);
}

/**
 * Evaluates whether an aisle can be selected for a new / resumed capture.
 * Does not block solely because assets exist or a prior job finished.
 */
export function evaluateAisleSelection(
  aisle: AisleSelectionInput | null | undefined,
  local: LocalCaptureHint = {},
): AisleSelectionResult {
  if (!aisle || typeof aisle !== 'object') {
    return { selectable: false, reason: 'invalid_data' };
  }
  const id = typeof aisle.id === 'string' ? aisle.id.trim() : '';
  if (!id) {
    return { selectable: false, reason: 'invalid_data' };
  }

  if (!normalizeIsActive(aisle.is_active ?? aisle.isActive)) {
    return { selectable: false, reason: 'inactive' };
  }

  if (local.exclusiveCaptureOnOtherAisle) {
    return { selectable: false, reason: 'capture_in_progress' };
  }

  // Same aisle with open local work is selectable so the operator can continue.
  if (local.exclusiveCaptureOpen) {
    return { selectable: true, reason: null };
  }

  const aisleStatus = normalizeStatus(aisle.status);
  if (AISLE_PROCESSING_STATUSES.has(aisleStatus)) {
    return { selectable: false, reason: 'processing' };
  }

  const jobStatus = readLatestJobStatus(aisle);
  if (ACTIVE_JOB_STATUSES.has(jobStatus)) {
    return { selectable: false, reason: 'processing' };
  }

  return { selectable: true, reason: null };
}

export function aisleBlockReasonLabel(reason: AisleBlockReason): string {
  switch (reason) {
    case 'inactive':
      return 'Pasillo inactivo';
    case 'processing':
      return 'Procesamiento en curso';
    case 'capture_in_progress':
      return 'Ya existe una captura activa';
    case 'not_authorized':
      return 'No tenés permisos para este pasillo';
    case 'invalid_data':
      return 'Datos de pasillo inválidos';
    default:
      return '';
  }
}
