import { describe, it, expect } from 'vitest';
import { getExecutionLogTxtUrl } from '../src/api/client';

describe('getExecutionLogTxtUrl', () => {
  it('builds the execution-log.txt path with encoded segments', () => {
    const u = getExecutionLogTxtUrl('inv-1', 'aisle-2', 'job/3');
    expect(u).toContain('/api/v3/inventories/inv-1/aisles/aisle-2/jobs/');
    expect(u).toContain('execution-log.txt');
    expect(u).toContain(encodeURIComponent('job/3'));
  });
});
