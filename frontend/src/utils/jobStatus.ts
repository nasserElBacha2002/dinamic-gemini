/**
 * Helpers for consistent job/status chip presentation in aisle processing UI.
 */

type ChipColor = 'default' | 'primary' | 'success' | 'error' | 'warning';

/**
 * Display label for a job status string (capitalized, known values normalized).
 */
export function getJobStatusLabel(status: string): string {
  const s = (status || '').trim().toLowerCase();
  if (!s) return '—';
  const known: Record<string, string> = {
    queued: 'Queued',
    running: 'Running',
    succeeded: 'Succeeded',
    failed: 'Failed',
  };
  return known[s] ?? status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

/**
 * MUI Chip color for job status. Use for job (not aisle) status chips.
 */
export function getJobStatusColor(status: string): ChipColor {
  const s = (status || '').trim().toLowerCase();
  switch (s) {
    case 'succeeded':
      return 'success';
    case 'failed':
      return 'error';
    case 'running':
    case 'queued':
      return 'primary';
    default:
      return 'default';
  }
}
