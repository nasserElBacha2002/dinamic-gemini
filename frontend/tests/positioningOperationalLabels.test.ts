import { describe, expect, it } from 'vitest';
import {
  ACTIVE_POLLING_STATES,
  presentationForProcessingState,
} from '../src/features/positioning/processingStateLabels';

describe('processingStateLabels', () => {
  it('maps RECOVERY_REQUIRED to recover action', () => {
    const p = presentationForProcessingState('RECOVERY_REQUIRED');
    expect(p.primaryAction).toMatch(/Recuperar/i);
    expect(p.label).toMatch(/Recuperación/i);
  });

  it('keeps polling set focused on active states', () => {
    expect(ACTIVE_POLLING_STATES.has('RUNNING')).toBe(true);
    expect(ACTIVE_POLLING_STATES.has('COMPLETED')).toBe(false);
  });
});
