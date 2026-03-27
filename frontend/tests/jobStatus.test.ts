import { describe, it, expect } from 'vitest';
import { getJobStatusLabel, jobStatusToBadgeSemantic } from '../src/utils/jobStatus';

describe('jobStatus', () => {
  it('maps known statuses to operator labels', () => {
    expect(getJobStatusLabel('succeeded')).toBe('Succeeded');
    expect(getJobStatusLabel('failed')).toBe('Failed');
    expect(getJobStatusLabel('running')).toBe('Running');
  });

  it('maps job statuses to stable StatusBadge semantics', () => {
    expect(jobStatusToBadgeSemantic('succeeded')).toBe('success');
    expect(jobStatusToBadgeSemantic('failed')).toBe('error');
    expect(jobStatusToBadgeSemantic('timed_out')).toBe('error');
    expect(jobStatusToBadgeSemantic('running')).toBe('info');
    expect(jobStatusToBadgeSemantic('queued')).toBe('info');
    expect(jobStatusToBadgeSemantic('cancel_requested')).toBe('warning');
    expect(jobStatusToBadgeSemantic('canceled')).toBe('warning');
    expect(jobStatusToBadgeSemantic('unknown')).toBe('neutral');
  });
});
