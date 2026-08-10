import { beforeEach, describe, expect, it, vi } from 'vitest';
import { issueProductLabels } from '../../src/api/productLabelsApi';

const apiRequestJson = vi.fn();

vi.mock('../../src/api/request', () => ({
  apiRequestJson: (...args: unknown[]) => apiRequestJson(...args),
}));

describe('productLabelsApi', () => {
  beforeEach(() => {
    apiRequestJson.mockReset();
    apiRequestJson.mockResolvedValue({ items: [] });
  });

  it('issueProductLabels passes a plain object body (not JSON.stringify)', async () => {
    await issueProductLabels('client-1', {
      internal_code: 'SKU-100',
      quantity: 4,
      count: 2,
    });
    expect(apiRequestJson).toHaveBeenCalledWith(
      expect.stringContaining('/api/v3/clients/client-1/product-labels'),
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
});
