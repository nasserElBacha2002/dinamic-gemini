/**
 * Helpers for consistent position status chip presentation in result views.
 */

type ChipColor = 'default' | 'primary' | 'success' | 'error' | 'warning';

/**
 * Display label for a position status string (user-friendly, known values normalized).
 */
export function getPositionStatusLabel(status: string): string {
  const s = (status || '').trim().toLowerCase();
  if (!s) return '—';
  const known: Record<string, string> = {
    detected: 'Detected',
    reviewed: 'Reviewed',
    corrected: 'Corrected',
    deleted: 'Deleted',
  };
  return known[s] ?? status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

/**
 * MUI Chip color for position status.
 */
export function getPositionStatusColor(status: string): ChipColor {
  const s = (status || '').trim().toLowerCase();
  switch (s) {
    case 'reviewed':
    case 'corrected':
      return 'success';
    case 'deleted':
      return 'error';
    case 'detected':
      return 'primary';
    default:
      return 'default';
  }
}
