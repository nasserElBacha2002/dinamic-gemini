import { describe, expect, it } from 'vitest';
import { resolveBrowseRunJobIds } from '../src/features/results/resolveBrowseRunJobId';

describe('resolveBrowseRunJobIds', () => {
  const jobs = [{ id: 'job-a' }, { id: 'job-b' }, { id: 'job-op' }];

  it('prefers explicit URL over operational and never jobs[0]', () => {
    const r = resolveBrowseRunJobIds({
      jobs,
      urlJobId: 'job-b',
      operationalJobId: 'job-op',
    });
    expect(r.explicitJobId).toBe('job-b');
    expect(r.displayJobId).toBe('job-b');
    expect(r.passExplicitJobIdToApi).toBe(true);
    expect(r.displayJobId).not.toBe(jobs[0].id);
  });

  it('uses operational for display when URL empty and does not pass job_id to API', () => {
    const r = resolveBrowseRunJobIds({
      jobs,
      urlJobId: null,
      operationalJobId: 'job-op',
    });
    expect(r.explicitJobId).toBeNull();
    expect(r.displayJobId).toBe('job-op');
    expect(r.passExplicitJobIdToApi).toBe(false);
    expect(r.displayJobId).not.toBe('job-a');
  });

  it('returns null display when no URL and no operational (legacy / backend SoT)', () => {
    const r = resolveBrowseRunJobIds({
      jobs,
      urlJobId: undefined,
      operationalJobId: null,
    });
    expect(r.displayJobId).toBeNull();
    expect(r.passExplicitJobIdToApi).toBe(false);
  });

  it('ignores URL job not in list (does not fall back to jobs[0])', () => {
    const r = resolveBrowseRunJobIds({
      jobs,
      urlJobId: 'missing',
      operationalJobId: 'job-op',
    });
    expect(r.explicitJobId).toBeNull();
    expect(r.displayJobId).toBe('job-op');
    expect(r.passExplicitJobIdToApi).toBe(false);
  });
});
