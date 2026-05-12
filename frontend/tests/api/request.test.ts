import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { ApiError } from '../../src/api/types';
import * as http from '../../src/api/http';
import { apiDownloadBlob, apiRequestJson } from '../../src/api/request';

describe('api/request apiRequestJson', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('GET does not add Content-Type and returns parsed JSON via handleResponse', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true, id: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    );
    const result = await apiRequestJson<{ ok: boolean; id: number }>('https://api.example/v1/items');
    expect(result).toEqual({ ok: true, id: 1 });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const init = fetchSpy.mock.calls[0][1] as RequestInit | undefined;
    expect(init?.method).toBeUndefined();
    const headers = new Headers(init?.headers);
    expect(headers.has('Content-Type')).toBe(false);
    expect(init?.body).toBeUndefined();
  });

  it('POST with object body sets Content-Type and JSON.stringify', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(
      new Response(JSON.stringify({ created: true }), { status: 201 })
    );
    await apiRequestJson<{ created: boolean }>('https://api.example/v1/items', {
      method: 'POST',
      body: { name: 'Example' },
    });
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(new Headers(init.headers).get('Content-Type')).toContain('application/json');
    expect(init.body).toBe(JSON.stringify({ name: 'Example' }));
  });

  it('does not override explicit Content-Type for JSON-serialized body', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(new Response('{}', { status: 200 }));
    await apiRequestJson('https://api.example/v1/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/vnd.api+json' },
      body: { a: 1 },
    });
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/vnd.api+json');
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
  });

  it('FormData does not set application/json and passes body through', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(new Response('{}', { status: 200 }));
    const form = new FormData();
    form.append('files', new Blob(['x']), 'f.txt');
    await apiRequestJson('https://api.example/upload', { method: 'POST', body: form });
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(form);
    const headers = new Headers(init.headers);
    expect(headers.get('Content-Type')).toBeNull();
  });

  it('strips conflicting application/json Content-Type when body is FormData', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(new Response('{}', { status: 200 }));
    const form = new FormData();
    await apiRequestJson('https://api.example/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: form,
    });
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Content-Type')).toBeNull();
    expect(init.body).toBe(form);
  });

  it('string body is sent raw without default Content-Type', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(new Response('{}', { status: 200 }));
    const raw = '{"x":1}';
    await apiRequestJson('https://api.example/v1', {
      method: 'POST',
      body: raw,
    });
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(raw);
    expect(new Headers(init.headers).has('Content-Type')).toBe(false);
  });

  it('string body keeps caller Content-Type when provided', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(new Response('{}', { status: 200 }));
    await apiRequestJson('https://api.example/v1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"x":1}',
    });
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json');
  });

  it('preserves custom non-Content-Type headers', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(new Response('{}', { status: 200 }));
    await apiRequestJson('https://api.example/v1', {
      headers: { 'X-Request-Id': 'abc' },
    });
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get('X-Request-Id')).toBe('abc');
  });

  it('error responses throw ApiError via handleResponse', async () => {
    vi.spyOn(http, 'protectedFetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'nope' }), { status: 400, statusText: 'Bad Request' })
    );
    await expect(apiRequestJson('https://api.example/x')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('api/request apiDownloadBlob', () => {
  beforeEach(() => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses Content-Disposition filename, clicks anchor, revokes URL', async () => {
    vi.spyOn(http, 'protectedFetch').mockResolvedValue(
      new Response(new Blob(['a,b']), {
        status: 200,
        headers: { 'Content-Disposition': 'attachment; filename="export.csv"' },
      })
    );
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const appendSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);

    await apiDownloadBlob('https://api.example/export', { fallbackFilename: 'fallback.csv' });

    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
    expect(appendSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
    appendSpy.mockRestore();
  });

  it('uses fallback filename when Content-Disposition is absent', async () => {
    vi.spyOn(http, 'protectedFetch').mockResolvedValue(new Response(new Blob(['x']), { status: 200 }));
    const appendSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node) => {
      if (node instanceof HTMLAnchorElement) {
        expect(node.download).toBe('fallback.csv');
      }
      return node;
    });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    await apiDownloadBlob('https://api.example/export', { fallbackFilename: 'fallback.csv' });

    appendSpy.mockRestore();
  });

  it('error response throws ApiError like existing download helpers', async () => {
    vi.spyOn(http, 'protectedFetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'forbidden' }), { status: 403 })
    );
    await expect(
      apiDownloadBlob('https://api.example/export', { fallbackFilename: 'x.csv' })
    ).rejects.toMatchObject({ status: 403 });
  });
});
