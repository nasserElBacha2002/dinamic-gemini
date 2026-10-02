import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequestJson = vi.fn();

vi.mock('../../src/api/request', () => ({
  apiRequestJson: (...args: unknown[]) => apiRequestJson(...args),
}));

async function loadIssueProductLabels(apiBase: string) {
  vi.stubEnv('VITE_API_BASE_URL', apiBase);
  vi.resetModules();
  return (await import('../../src/api/productLabelsApi')).issueProductLabels;
}

describe('productLabelsApi', () => {
  beforeEach(() => {
    apiRequestJson.mockReset();
    apiRequestJson.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('uses VITE_API_BASE_URL and passes a plain object body', async () => {
    const issueProductLabels = await loadIssueProductLabels('https://api.dinamiceducation.com');

    await issueProductLabels('client-1', {
      internal_code: 'SKU-100',
      quantity: 4,
      count: 2,
    });
    expect(apiRequestJson).toHaveBeenCalledWith(
      'https://api.dinamiceducation.com/api/v3/clients/client-1/product-labels',
      expect.objectContaining({
        method: 'POST',
        body: {
          internal_code: 'SKU-100',
          quantity: 4,
          count: 2,
        },
      })
    );
    const [, opts] = apiRequestJson.mock.calls[0];
    expect(typeof opts.body).toBe('object');
    expect(opts.body).not.toBeTypeOf('string');
  });

  it('preserves the relative API URL when VITE_API_BASE_URL is empty', async () => {
    const issueProductLabels = await loadIssueProductLabels('');

    await issueProductLabels('client/with spaces', {
      internal_code: 'SKU-200',
      quantity: 8,
    });

    expect(apiRequestJson).toHaveBeenCalledWith(
      '/api/v3/clients/client%2Fwith%20spaces/product-labels',
      expect.objectContaining({
        method: 'POST',
        body: {
          internal_code: 'SKU-200',
          quantity: 8,
          count: 1,
        },
      })
    );
  });
});
