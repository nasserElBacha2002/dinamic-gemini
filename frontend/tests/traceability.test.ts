/**
 * Epic 3.1.B — Traceability helper tests.
 */

import { describe, it, expect } from 'vitest';
import {
  TRACEABILITY_STATUSES,
  isTraceabilityStatus,
  toTraceabilityStatus,
} from '../src/utils/traceability';

describe('TRACEABILITY_STATUSES', () => {
  it('contains exactly the four allowed values', () => {
    expect(TRACEABILITY_STATUSES).toEqual(['valid', 'missing', 'invalid', 'unvalidated']);
  });
});

describe('isTraceabilityStatus', () => {
  it('returns true for each allowed value', () => {
    expect(isTraceabilityStatus('valid')).toBe(true);
    expect(isTraceabilityStatus('missing')).toBe(true);
    expect(isTraceabilityStatus('invalid')).toBe(true);
    expect(isTraceabilityStatus('unvalidated')).toBe(true);
  });

  it('returns false for null and undefined', () => {
    expect(isTraceabilityStatus(null)).toBe(false);
    expect(isTraceabilityStatus(undefined)).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(isTraceabilityStatus('')).toBe(false);
  });

  it('returns false for unknown strings', () => {
    expect(isTraceabilityStatus('unknown')).toBe(false);
    expect(isTraceabilityStatus('VALID')).toBe(false);
    expect(isTraceabilityStatus('valid ')).toBe(false);
  });
});

describe('toTraceabilityStatus', () => {
  it('returns value for allowed strings', () => {
    expect(toTraceabilityStatus('valid')).toBe('valid');
    expect(toTraceabilityStatus('missing')).toBe('missing');
    expect(toTraceabilityStatus('invalid')).toBe('invalid');
    expect(toTraceabilityStatus('unvalidated')).toBe('unvalidated');
  });

  it('returns null for null and undefined', () => {
    expect(toTraceabilityStatus(null)).toBe(null);
    expect(toTraceabilityStatus(undefined)).toBe(null);
  });

  it('returns null for non-strings', () => {
    expect(toTraceabilityStatus(123)).toBe(null);
    expect(toTraceabilityStatus({})).toBe(null);
  });

  it('returns null for unknown strings', () => {
    expect(toTraceabilityStatus('other')).toBe(null);
  });
});
