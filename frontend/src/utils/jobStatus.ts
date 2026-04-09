/**
 * Helpers for consistent job / processing status presentation in aisle UI.
 */

import type { JobStatus } from '../api/types';
import type { StatusBadgeSemantic } from '../components/ui/StatusBadge';
import i18n from '../i18n';

type ChipColor = 'default' | 'primary' | 'success' | 'error' | 'warning';
type JobStatusLike = JobStatus | string;

/**
 * Display label for a job status string (localized).
 */
export function getJobStatusLabel(status: JobStatusLike): string {
  const s = (status || '').trim().toLowerCase();
  if (!s) return i18n.t('common.em_dash');
  const key = `jobs.status.${s}`;
  if (i18n.exists(key)) return i18n.t(key);
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

/**
 * MUI Chip color for job status. Use for job (not aisle) status chips.
 */
export function getJobStatusColor(status: JobStatusLike): ChipColor {
  const s = (status || '').trim().toLowerCase();
  switch (s) {
    case 'succeeded':
      return 'success';
    case 'failed':
    case 'timed_out':
      return 'error';
    case 'running':
    case 'starting':
    case 'queued':
      return 'primary';
    case 'cancel_requested':
    case 'canceled':
      return 'warning';
    default:
      return 'default';
  }
}

/** Maps v3 job status to shared `StatusBadge` semantics (Sprint 5.3). */
export function jobStatusToBadgeSemantic(status: JobStatusLike): StatusBadgeSemantic {
  const s = (status || '').trim().toLowerCase();
  switch (s) {
    case 'succeeded':
      return 'success';
    case 'failed':
    case 'timed_out':
      return 'error';
    case 'running':
    case 'starting':
    case 'queued':
      return 'info';
    case 'cancel_requested':
    case 'canceled':
      return 'warning';
    default:
      return 'neutral';
  }
}
