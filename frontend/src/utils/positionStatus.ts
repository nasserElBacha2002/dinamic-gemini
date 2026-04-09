/**
 * Helpers for consistent position status chip presentation in result views.
 */

import i18n from '../i18n';

type ChipColor = 'default' | 'primary' | 'success' | 'error' | 'warning';

/**
 * Display label for a position status string (localized).
 */
export function getPositionStatusLabel(status: string): string {
  const s = (status || '').trim().toLowerCase();
  if (!s) return i18n.t('common.em_dash');
  const key = `positions.status.${s}`;
  if (i18n.exists(key)) return i18n.t(key);
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
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
