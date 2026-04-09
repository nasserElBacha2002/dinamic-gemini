/**
 * Helpers for consistent aisle status presentation in inventory/aisle UI.
 */

import type { StatusBadgeSemantic } from '../components/ui/StatusBadge';
import i18n from '../i18n';

type ChipColor = 'default' | 'primary' | 'success' | 'error' | 'warning';

/**
 * Display label for an aisle status string (localized).
 */
export function getAisleStatusLabel(status: string): string {
  const s = (status || '').trim().toLowerCase();
  if (!s) return i18n.t('common.em_dash');
  const key = `aisle.status.${s}`;
  if (i18n.exists(key)) return i18n.t(key);
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
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

/** Maps aisle lifecycle status to shared `StatusBadge` semantics (Sprint 5.3). */
export function aisleStatusToBadgeSemantic(status: string): StatusBadgeSemantic {
  const s = (status || '').trim().toLowerCase();
  if (!s) return 'neutral';
  switch (s) {
    case 'failed':
      return 'error';
    case 'processed':
    case 'in_review':
    case 'completed':
      return 'success';
    case 'queued':
    case 'processing':
      return 'info';
    case 'created':
    case 'assets_uploaded':
    default:
      return 'neutral';
  }
}
