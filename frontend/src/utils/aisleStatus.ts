/**
 * Helpers for consistent aisle status presentation in inventory/aisle UI.
 */

import type { StatusBadgeSemantic } from '../components/ui/StatusBadge';

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
