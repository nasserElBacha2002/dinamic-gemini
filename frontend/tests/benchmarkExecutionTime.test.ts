import { describe, it, expect } from 'vitest';
import {
  formatExecutionDurationHuman,
  formatSignedDurationHuman,
  wallClockSecondsFromJobTimestamps,
} from '../src/utils/benchmarkExecutionTime';

describe('benchmarkExecutionTime', () => {
  it('formats sub-minute durations', () => {
    expect(formatExecutionDurationHuman(12.4)).toBe('12.4s');
    expect(formatExecutionDurationHuman(10)).toBe('10s');
  });

  it('formats minute+ durations', () => {
    expect(formatExecutionDurationHuman(60)).toBe('1m');
    expect(formatExecutionDurationHuman(62)).toBe('1m 02s');
  });

  it('computes wall seconds from ISO timestamps', () => {
    expect(
      wallClockSecondsFromJobTimestamps('2026-01-01T12:00:00Z', '2026-01-01T12:00:10.400Z')
    ).toBeCloseTo(10.4, 5);
    expect(wallClockSecondsFromJobTimestamps(null, '2026-01-01T12:00:10Z')).toBeNull();
  });

  it('formats signed deltas', () => {
    expect(formatSignedDurationHuman(3.2)).toBe('+3.2s');
    expect(formatSignedDurationHuman(-5)).toBe('-5s');
  });
});
