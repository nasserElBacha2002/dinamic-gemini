/**
 * Phase 5 — human labels for published position assignment statuses.
 */

import type { TFunction } from 'i18next';

export function formatAislePositionDisplay(
  t: TFunction,
  args: {
    aislePositionName: string | null | undefined;
    positionAssignmentStatus: string | null | undefined;
    positionAssignmentSource?: string | null;
    positionCode: string | null | undefined;
    aislePositionAssigned?: boolean;
  }
): string {
  const name = (args.aislePositionName ?? '').trim();
  if (name) {
    return args.positionAssignmentSource === 'MANUAL'
      ? `${name} ${t('results.position_assignment.manual_marker')}`
      : name;
  }
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
    case 'ASSIGNED_MANUAL':
      return t('results.position_assignment.status.assigned_manual');
    case 'UNASSIGNED_MANUAL':
      return t('results.position_assignment.status.unassigned_manual');
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

export function formatAutomaticPositionSecondary(
  t: TFunction,
  args: {
    effectivePositionName: string | null | undefined;
    automaticPositionName: string | null | undefined;
    positionAssignmentSource: string | null | undefined;
  }
): string | null {
  if (args.positionAssignmentSource !== 'MANUAL') return null;
  const automatic = (args.automaticPositionName ?? '').trim();
  const effective = (args.effectivePositionName ?? '').trim();
  if (!automatic || automatic === effective) return null;
  return t('results.position_assignment.automatic_secondary', { position: automatic });
}
