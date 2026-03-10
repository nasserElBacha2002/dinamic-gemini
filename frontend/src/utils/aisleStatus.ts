/**
 * Helpers for consistent aisle status chip presentation in inventory/aisle UI.
 */

type ChipColor = 'default' | 'primary' | 'success' | 'error' | 'warning';

/**
 * Display label for an aisle status string (user-friendly, known values normalized).
 */
export function getAisleStatusLabel(status: string): string {
  const s = (status || '').trim().toLowerCase();
  if (!s) return '—';
  const known: Record<string, string> = {
    created: 'Created',
    assets_uploaded: 'Assets uploaded',
    queued: 'Queued',
    processing: 'Processing',
    processed: 'Processed',
    in_review: 'In review',
    completed: 'Completed',
    failed: 'Failed',
  };
  return known[s] ?? status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

/**
 * MUI Chip color for aisle status.
 */
export function getAisleStatusColor(status: string): ChipColor {
  const s = (status || '').trim().toLowerCase();
  switch (s) {
    case 'failed':
      return 'error';
    case 'processed':
    case 'in_review':
    case 'completed':
      return 'success';
    case 'processing':
    case 'queued':
      return 'primary';
    case 'created':
    case 'assets_uploaded':
    default:
      return 'default';
  }
}
