import { describe, it, expect } from 'vitest';
import { ApiError } from '../../src/api/types';
import { handleResponse } from '../../src/api/http';

describe('api/http handleResponse', () => {
  it('throws ApiError preserving status, code and detail', async () => {
    const response = new Response(JSON.stringify({ code: 'INVENTORY_NOT_FOUND', detail: 'Not found' }), {
      status: 404,
      statusText: 'Not Found',
      headers: { 'Content-Type': 'application/json' },
    });

    try {
      await handleResponse(response);
      throw new Error('Expected handleResponse to throw');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      const apiError = error as ApiError;
      expect(apiError.status).toBe(404);
      expect(apiError.data?.code).toBe('INVENTORY_NOT_FOUND');
      expect(apiError.data?.detail).toBe('Not found');
    }
  });

  it('handles validation detail arrays', async () => {
    const response = new Response(JSON.stringify({ detail: [{ msg: 'field required' }] }), {
      status: 422,
      statusText: 'Unprocessable Entity',
      headers: { 'Content-Type': 'application/json' },
    });

    await expect(handleResponse(response)).rejects.toMatchObject({ message: 'field required' });
  });

  it('handles non-json error bodies without crashing', async () => {
    const response = new Response('gateway timeout', {
      status: 504,
      statusText: 'Gateway Timeout',
      headers: { 'Content-Type': 'text/plain' },
    });

    await expect(handleResponse(response)).rejects.toMatchObject({
      status: 504,
      message: 'gateway timeout',
    });
  });
});

