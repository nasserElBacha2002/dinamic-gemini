import { describe, expect, it } from 'vitest';
import type { TFunction } from 'i18next';
import {
  formatAislePositionDisplay,
  formatAutomaticPositionSecondary,
  formatPositionAssignmentStatusLabel,
} from '../src/features/results/utils/positionAssignmentDisplay';

const messages: Record<string, string> = {
  'results.position_assignment.manual_marker': '(manual)',
  'results.position_assignment.automatic_secondary': 'Automática: {{position}}',
  'results.position_assignment.status.assigned_manual': 'Asignada manualmente',
  'results.position_assignment.status.unassigned_manual': 'Quitada manualmente',
};

const t = ((key: string, options?: Record<string, unknown>) =>
  (messages[key] ?? key).replace(
    '{{position}}',
    String(options?.position ?? '')
  )) as TFunction;

describe('position assignment display', () => {
  it('marks the effective manual position', () => {
    expect(
      formatAislePositionDisplay(t, {
        aislePositionName: 'P-02',
        positionAssignmentStatus: 'ASSIGNED_MANUAL',
        positionAssignmentSource: 'MANUAL',
        positionCode: null,
      })
    ).toBe('P-02 (manual)');
  });

  it('shows a differing automatic position as secondary', () => {
    expect(
      formatAutomaticPositionSecondary(t, {
        effectivePositionName: 'P-02',
        automaticPositionName: 'P-01',
        positionAssignmentSource: 'MANUAL',
      })
    ).toBe('Automática: P-01');
  });

  it('labels manual assigned and unassigned states', () => {
    expect(formatPositionAssignmentStatusLabel(t, 'ASSIGNED_MANUAL')).toBe(
      'Asignada manualmente'
    );
    expect(formatPositionAssignmentStatusLabel(t, 'UNASSIGNED_MANUAL')).toBe(
      'Quitada manualmente'
    );
  });
});
