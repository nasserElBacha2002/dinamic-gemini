/**
 * Derive operator-facing processing state from latest job terminal metadata.
 * Latest job terminal state takes priority over aisle.status for active UI.
 */

import type { Aisle } from '../api/types';

export type EffectiveProcessingDisplayState =
  | 'processing'
  | 'failed'
  | 'canceled'
  | 'completed'
  | 'completed_with_finalization_warning';

export interface JobLikeForDisplay {
  status?: string | null;
  finalization_status?: string | null;
  current_finalization_step?: string | null;
  failure_code?: string | null;
  finalization_error_code?: string | null;
}

function normalizeStatus(value: string | null | undefined): string {
  return String(value ?? '').trim().toLowerCase();
}

export function deriveEffectiveJobDisplayState(
  latestJob: JobLikeForDisplay | null | undefined
): EffectiveProcessingDisplayState {
  const status = normalizeStatus(latestJob?.status);
  if (status === 'failed') return 'failed';
  if (status === 'canceled') return 'canceled';
  if (status === 'succeeded') {
    if (normalizeStatus(latestJob?.finalization_status) === 'failed') {
      return 'completed_with_finalization_warning';
    }
    return 'completed';
  }
  return 'processing';
}

export function deriveAisleEffectiveDisplayState(
  aisle: Pick<Aisle, 'status'> | null | undefined,
  latestJob: JobLikeForDisplay | null | undefined
): EffectiveProcessingDisplayState {
  const jobState = deriveEffectiveJobDisplayState(latestJob);
  if (jobState !== 'processing') {
    return jobState;
  }
  const aisleStatus = normalizeStatus(aisle?.status);
  if (aisleStatus === 'failed') return 'failed';
  if (aisleStatus === 'processing' || aisleStatus === 'queued') return 'processing';
  return 'processing';
}

export function isJobTerminalStatus(status: string | null | undefined): boolean {
  const s = normalizeStatus(status);
  return s === 'succeeded' || s === 'failed' || s === 'canceled';
}

export function isJobProcessingActive(latestJob: JobLikeForDisplay | null | undefined): boolean {
  return !isJobTerminalStatus(latestJob?.status);
}

export function isOperationalReconciliationPending(
  latestJob: JobLikeForDisplay | null | undefined
): boolean {
  const status = normalizeStatus(latestJob?.status);
  if (status !== 'succeeded') return false;
  const fin = normalizeStatus(latestJob?.finalization_status);
  return fin === 'failed' || fin === 'in_progress';
}

/** Primary job polling — stops on terminal job status. */
export function shouldPollJobDetail(
  latestJob: JobLikeForDisplay | null | undefined,
  elapsedMs: number,
  maxFallbackMs = 30 * 60 * 1000
): boolean {
  if (isJobProcessingActive(latestJob)) {
    return elapsedMs < maxFallbackMs;
  }
  if (isOperationalReconciliationPending(latestJob)) {
    return elapsedMs < 120_000;
  }
  return false;
}
