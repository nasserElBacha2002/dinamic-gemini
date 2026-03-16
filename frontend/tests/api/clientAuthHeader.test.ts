/**
 * v3.2.1 — API client sends Authorization header for protected requests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getInventories } from '../../src/api/client';

const mockGetStoredToken = vi.fn();
vi.mock('../../src/features/auth/storage', () => ({
  getStoredToken: () => mockGetStoredToken(),
}));

describe('API client auth header', () => {
  let fetchCalls: { url: string; init?: RequestInit }[] = [];

  beforeEach(() => {
    fetchCalls = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString();
        fetchCalls.push({ url, init });
        return Promise.resolve(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));
      })
    );
  });

  it('sends Authorization Bearer when token exists', async () => {
    mockGetStoredToken.mockReturnValue('stored-jwt-token');
    await getInventories();
    expect(fetchCalls.length).toBe(1);
    const headers = fetchCalls[0].init?.headers;
    expect(headers).toBeDefined();
    const authHeader = headers instanceof Headers ? headers.get('Authorization') : (headers as Record<string, string>)?.Authorization;
    expect(authHeader).toBe('Bearer stored-jwt-token');
  });

  it('does not send Authorization when no token', async () => {
    mockGetStoredToken.mockReturnValue(null);
    await getInventories();
    expect(fetchCalls.length).toBe(1);
    const headers = fetchCalls[0].init?.headers;
    const authHeader = headers instanceof Headers ? headers.get('Authorization') : (headers as Record<string, string>)?.Authorization;
    expect(authHeader).toBeFalsy();
  });
});
