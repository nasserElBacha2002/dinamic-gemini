/**
 * Phase 5 — human labels for published position assignment statuses.
 */

import type { TFunction } from 'i18next';

export function formatAislePositionDisplay(
  t: TFunction,
  args: {
    aislePositionName: string | null | undefined;
    positionAssignmentStatus: string | null | undefined;
    positionCode: string | null | undefined;
    aislePositionAssigned?: boolean;
  }
): string {
  const name = (args.aislePositionName ?? '').trim();
  if (name) return name;
  const status = (args.positionAssignmentStatus ?? '').trim();
  if (status === 'NO_RECONCILIATION') {
    return t('results.position_assignment.no_reconciliation');
  }
  if (status.startsWith('UNASSIGNED') || args.aislePositionAssigned === false) {
    return t('results.position_assignment.unassigned');
  }
  const code = (args.positionCode ?? '').trim();
  return code || t('results.position_assignment.unassigned');
}

export function formatPositionAssignmentStatusLabel(
  t: TFunction,
  status: string | null | undefined
): string {
  const s = (status ?? '').trim();
  switch (s) {
    case 'ASSIGNED_AUTOMATIC':
      return t('results.position_assignment.status.assigned_automatic');
    case 'UNASSIGNED_NO_PREVIOUS_POSITION':
      return t('results.position_assignment.status.unassigned_no_previous');
    case 'UNASSIGNED_AFTER_AMBIGUOUS_POSITION':
      return t('results.position_assignment.status.unassigned_ambiguous');
    case 'UNASSIGNED_INVALID_POSITION':
      return t('results.position_assignment.status.unassigned_invalid');
    case 'UNASSIGNED_UNORDERED_ASSET':
      return t('results.position_assignment.status.unassigned_unordered');
    case 'NO_RECONCILIATION':
      return t('results.position_assignment.status.no_reconciliation');
    case 'RECONCILIATION_STALE':
      return t('results.position_assignment.status.stale');
    default:
      return s || t('common.em_dash');
  }
}
