/**
 * Inventory list row presentation — wire status → StatusBadge semantics (Re diseño 3.3 §6.3, §11).
 */

import type { StatusBadgeSemantic } from '../components/ui/StatusBadge';
import i18n from '../i18n';

export function formatInventoryStatusLabel(raw: string): string {
  const s = raw.trim().toLowerCase();
  if (!s) return i18n.t('common.em_dash');
  const key = `inventory.status.${s}`;
  if (i18n.exists(key)) return i18n.t(key);
  return raw
    .split('_')
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : ''))
    .join(' ');
}

export function inventoryStatusToBadgeSemantic(status: string): StatusBadgeSemantic {
  const s = status.trim().toLowerCase();
  if (s === 'completed') return 'success';
  if (s === 'failed') return 'error';
  if (s === 'draft') return 'neutral';
  if (s === 'processing' || s === 'in_review') return 'info';
  return 'neutral';
}
