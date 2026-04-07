import { describe, it, expect } from 'vitest';
import { getAisleExecutionLogTxtUrl, getExecutionLogTxtUrl } from '../src/api/client';

describe('getExecutionLogTxtUrl', () => {
  it('builds the execution-log.txt path with encoded segments', () => {
    const u = getExecutionLogTxtUrl('inv-1', 'aisle-2', 'job/3');
    expect(u).toContain('/api/v3/inventories/inv-1/aisles/aisle-2/jobs/');
    expect(u).toContain('execution-log.txt');
    expect(u).toContain(encodeURIComponent('job/3'));
  });
});

describe('getAisleExecutionLogTxtUrl', () => {
  it('builds the aisle-level execution-log.txt path', () => {
    const u = getAisleExecutionLogTxtUrl('inv-1', 'aisle/x');
    expect(u).toContain('/api/v3/inventories/inv-1/aisles/');
    expect(u).toContain('execution-log.txt');
    expect(u).toContain(encodeURIComponent('aisle/x'));
  });
});
