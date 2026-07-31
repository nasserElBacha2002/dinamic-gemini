import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clientPositionLabelDownloadUrl,
  clientPositionLabelPreviewUrl,
  createClientPositionLabel,
  invalidateClientPositionLabel,
  listClientPositionLabels,
  updateClientPositionLabel,
} from '../../src/api/clientPositionLabelsApi';

const apiRequestJson = vi.fn();

vi.mock('../../src/api/request', () => ({
  apiRequestJson: (...args: unknown[]) => apiRequestJson(...args),
  apiDownloadBlob: vi.fn(),
}));

describe('clientPositionLabelsApi', () => {
  beforeEach(() => {
    apiRequestJson.mockReset();
    apiRequestJson.mockResolvedValue({ id: 'lbl-1', name: '01' });
  });

  it('createClientPositionLabel passes a plain object body (not JSON.stringify)', async () => {
    const body = { name: '01', description: null };
    await createClientPositionLabel('client-1', body);
    expect(apiRequestJson).toHaveBeenCalledWith(
      expect.stringContaining('/api/v3/clients/client-1/position-labels'),
      expect.objectContaining({
        method: 'POST',
        body,
      })
    );
    const [, opts] = apiRequestJson.mock.calls[0];
    expect(typeof opts.body).toBe('object');
    expect(opts.body).not.toBeTypeOf('string');
  });

  it('updateClientPositionLabel passes a plain object body', async () => {
    const body = { name: '02' };
    await updateClientPositionLabel('client-1', 'lbl-1', body);
    const [, opts] = apiRequestJson.mock.calls[0];
    expect(opts.body).toEqual(body);
    expect(typeof opts.body).toBe('object');
  });

  it('invalidateClientPositionLabel passes a plain object body', async () => {
    await invalidateClientPositionLabel('client-1', 'lbl-1', 'moved');
    const [, opts] = apiRequestJson.mock.calls[0];
    expect(opts.body).toEqual({ reason: 'moved' });
    expect(typeof opts.body).toBe('object');
  });

  it('listClientPositionLabels builds a valid query string (tuple entries)', async () => {
    apiRequestJson.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
      total_pages: 0,
    });
    await listClientPositionLabels('client-1', { page: 1, page_size: 100, search: '01' });
    const [url] = apiRequestJson.mock.calls[0];
    expect(url).toContain('/api/v3/clients/client-1/position-labels?');
    expect(url).toContain('page=1');
    expect(url).toContain('page_size=100');
    expect(url).toContain('search=01');
  });

  it('preview/download URLs include format and preset query params', () => {
    expect(clientPositionLabelPreviewUrl('c1', 'l1', { format: 'PNG', preset: 'MM_100x100' })).toMatch(
      /\/preview\?format=PNG&preset=MM_100x100$/
    );
    expect(clientPositionLabelDownloadUrl('c1', 'l1', { format: 'PDF', preset: 'MM_100x100' })).toMatch(
      /\/download\?format=PDF&preset=MM_100x100$/
    );
  });
});
