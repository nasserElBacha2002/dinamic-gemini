/**
 * Epic 3.1.B — getJobEntities response normalization tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getJobEntities } from '../src/api/client';

describe('getJobEntities', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('returns entities as array when backend returns entities array', async () => {
    const entities = [{ entity_uid: 'e1', entity_type: 'product' }];
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ entities })),
    });
    const result = await getJobEntities('job-1');
    expect(result.entities).toEqual(entities);
    expect(Array.isArray(result.entities)).toBe(true);
  });

  it('normalizes missing entities to empty array', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({})),
    });
    const result = await getJobEntities('job-1');
    expect(result.entities).toEqual([]);
    expect(Array.isArray(result.entities)).toBe(true);
  });

  it('preserves other backend fields when present', async () => {
    const payload = {
      entities: [{ entity_uid: 'e1', entity_type: 'product' }],
      traceability_summary: {
        total_entities: 1,
        valid: 1,
        missing: 0,
        invalid: 0,
        unvalidated: 0,
      },
      meta: { total: 1 },
      next_page: null,
    };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify(payload)),
    });
    const result = await getJobEntities('job-1');
    expect(result.entities).toHaveLength(1);
    expect(result.traceability_summary).toEqual({
      total_entities: 1,
      valid: 1,
      missing: 0,
      invalid: 0,
      unvalidated: 0,
    });
  });

  it('sends traceability_status query param when provided', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ entities: [] })),
    });
    await getJobEntities('job-1', { traceability_status: 'missing' });
    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[0]).toContain('traceability_status=missing');
  });

  it('does not add traceability_status when null or empty', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ entities: [] })),
    });
    await getJobEntities('job-1');
    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[0]).not.toContain('traceability_status');
  });

  it('normalizes non-array entities to empty array', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ entities: null })),
    });
    const result = await getJobEntities('job-1');
    expect(result.entities).toEqual([]);
  });
});
