import { describe, it, expect } from 'vitest';
import { buildCaptureSessionsQuery } from '../../src/features/ingestionSessions/api/captureSessionsApi';

describe('buildCaptureSessionsQuery', () => {
  const base = { inventoryId: 'inv-1' };

  it('returns empty string when only inventory-scoped fields would apply (query is path-only)', () => {
    expect(buildCaptureSessionsQuery({ ...base })).toBe('');
  });

  it('omits aisle_id and status when blank after trim', () => {
    expect(buildCaptureSessionsQuery({ ...base, aisleId: '   ', statusCsv: '' })).toBe('');
  });

  it('trims aisle_id and status', () => {
    const qs = buildCaptureSessionsQuery({ ...base, aisleId: '  a1  ', statusCsv: '  open,pending  ' });
    const p = new URLSearchParams(qs.startsWith('?') ? qs.slice(1) : qs);
    expect(p.get('aisle_id')).toBe('a1');
    expect(p.get('status')).toBe('open,pending');
  });

  it('omits page when 0 but keeps page_size', () => {
    expect(buildCaptureSessionsQuery({ ...base, page: 0, pageSize: 10 })).toBe('?page_size=10');
  });

  it('preserves param order', () => {
    expect(
      buildCaptureSessionsQuery({
        ...base,
        aisleId: 'a1',
        statusCsv: 'x',
        page: 2,
        pageSize: 20,
      })
    ).toBe('?aisle_id=a1&status=x&page=2&page_size=20');
  });
});
