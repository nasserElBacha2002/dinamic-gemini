import { describe, it, expect } from 'vitest';
import { aisleStatusToBadgeSemantic, getAisleStatusLabel } from '../src/utils/aisleStatus';

describe('aisleStatus', () => {
  it('normalizes aisle labels', () => {
    expect(getAisleStatusLabel('processed')).toBe('Processed');
    expect(getAisleStatusLabel('in_review')).toBe('In review');
  });

  it('maps aisle lifecycle to StatusBadge semantics', () => {
    expect(aisleStatusToBadgeSemantic('failed')).toBe('error');
    expect(aisleStatusToBadgeSemantic('processed')).toBe('success');
    expect(aisleStatusToBadgeSemantic('processing')).toBe('info');
    expect(aisleStatusToBadgeSemantic('created')).toBe('neutral');
  });
});
