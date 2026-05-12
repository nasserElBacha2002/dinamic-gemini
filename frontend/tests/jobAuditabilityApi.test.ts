import { describe, it, expect } from 'vitest';
import { V3_INVENTORIES_BASE } from '../src/constants/v3ApiPaths';
import { getJobAuditabilityPath } from '../src/api/jobsApi';

describe('getJobAuditabilityPath', () => {
  it('builds the auditability URL under inventories/aisles/jobs', () => {
    const p = getJobAuditabilityPath('inv-1', 'aisle-2', 'job/3');
    expect(p).toContain(`${V3_INVENTORIES_BASE}/`);
    expect(p).toContain('/aisles/');
    expect(p).toContain('/jobs/');
    expect(p).toContain('/auditability');
    expect(p).toContain(encodeURIComponent('job/3'));
  });
});
