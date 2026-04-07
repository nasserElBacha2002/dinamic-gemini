import { describe, it, expect } from 'vitest';
import { resolveDisplayFinishedAt } from '../src/utils/jobDisplayTimestamps';

describe('resolveDisplayFinishedAt', () => {
  it('returns null for non-terminal jobs', () => {
    expect(
      resolveDisplayFinishedAt({
        status: 'running',
        started_at: '2026-01-01T10:00:00.000Z',
        finished_at: null,
      })
    ).toBeNull();
  });

  it('uses coherent job.finished_at when it is after started and step started', () => {
    expect(
      resolveDisplayFinishedAt({
        status: 'succeeded',
        started_at: '2026-01-01T10:00:00.000Z',
        current_step_started_at: '2026-01-01T10:05:00.000Z',
        finished_at: '2026-01-01T10:30:00.000Z',
      })
    ).toBe('2026-01-01T10:30:00.000Z');
  });

  it('falls back to terminal log event when finished_at is before step started', () => {
    const job = {
      status: 'succeeded',
      started_at: '2026-01-01T10:00:00.000Z',
      current_step_started_at: '2026-01-01T10:20:00.000Z',
      finished_at: '2026-01-01T10:05:00.000Z',
    };
    const events = [
      { ts: '2026-01-01T10:15:00.000Z', stage: 'Pipeline', level: 'info', message: 'job.heartbeat' },
      { ts: '2026-01-01T10:25:00.000Z', stage: 'Pipeline', level: 'info', message: 'job.succeeded' },
    ];
    expect(resolveDisplayFinishedAt(job, events)).toBe('2026-01-01T10:25:00.000Z');
  });
});
