/**
 * Epic 3 — Tests for visible traceability display mapper.
 */

import { describe, it, expect } from 'vitest';
import { visibleTraceabilityToApiStatus } from '../src/features/results/utils/traceabilityDisplay';

describe('visibleTraceabilityToApiStatus', () => {
  it('maps VALID to valid', () => {
    expect(visibleTraceabilityToApiStatus('VALID')).toBe('valid');
  });

  it('maps MISSING to missing', () => {
    expect(visibleTraceabilityToApiStatus('MISSING')).toBe('missing');
  });

  it('maps INVALID to invalid', () => {
    expect(visibleTraceabilityToApiStatus('INVALID')).toBe('invalid');
  });

  it('maps UNVALIDATED to unvalidated', () => {
    expect(visibleTraceabilityToApiStatus('UNVALIDATED')).toBe('unvalidated');
  });
});
