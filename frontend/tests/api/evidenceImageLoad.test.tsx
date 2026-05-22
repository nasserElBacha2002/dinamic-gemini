/**
 * Evidence image load — JSON image-display-url + optional /file blob; differentiated error handling.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { fetchEvidenceImageDisplay } from '../../src/api/client';
import { useEvidenceImageLoad } from '../../src/features/results/hooks/useEvidenceImageLoad';
import * as authStorage from '../../src/features/auth/storage';

vi.mock('../../src/features/auth/storage', () => ({
  getStoredToken: vi.fn(),
}));

function ensureBlobUrlSupport() {
  if (typeof (URL as unknown as { createObjectURL?: (b: Blob) => string }).createObjectURL !== 'function') {
    (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = vi.fn(() => 'blob:test-mock-url');
  }
  if (typeof (URL as unknown as { revokeObjectURL?: (u: string) => void }).revokeObjectURL !== 'function') {
    (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL = vi.fn();
  }
}

const SPEC = {
  inventoryId: 'inv-1',
  aisleId: 'aisle-1',
  assetId: 'asset-1',
  jobId: null as string | null,
};

describe('fetchEvidenceImageDisplay', () => {
  beforeEach(() => {
    ensureBlobUrlSupport();
    vi.mocked(authStorage.getStoredToken).mockReturnValue(null);
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network error'))));
  });

  it('requests image-display-url with Authorization when token is set', async () => {
    vi.mocked(authStorage.getStoredToken).mockReturnValue('test-jwt-token');
    const fetchMock = vi.fn((_url: string) => {
      if (typeof _url === 'string' && _url.includes('image-display-url')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              image_url: 'https://s3.example/signed',
              requires_authenticated_fetch: false,
              display_strategy: 'presigned_url',
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        );
      }
      return Promise.reject(new Error('unexpected url'));
    });
    vi.stubGlobal('fetch', fetchMock);
    await fetchEvidenceImageDisplay(SPEC);
    expect(fetchMock).toHaveBeenCalled();
    const jsonCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('image-display-url')) as
      | [string, RequestInit]
      | undefined;
    expect(jsonCall).toBeDefined();
    const init = jsonCall![1];
    const headers = init.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer test-jwt-token');
  });

  it('returns presigned imageSrc when JSON includes image_url', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              image_url: 'https://s3.example/bucket/k?sig=1',
              requires_authenticated_fetch: false,
              display_strategy: 'presigned_url',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        )
      )
    );
    const result = await fetchEvidenceImageDisplay(SPEC);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.imageSrc).toBe('https://s3.example/bucket/k?sig=1');
      expect(result.revoke).toBeUndefined();
    }
  });

  it('GETs /file with Bearer when JSON requests authenticated fetch', async () => {
    vi.mocked(authStorage.getStoredToken).mockReturnValue('tok');
    const fetchMock = vi
      .fn()
      .mockImplementationOnce((url: string) => {
        expect(String(url)).toContain('image-display-url');
        return Promise.resolve(
          new Response(
            JSON.stringify({
              image_url: null,
              requires_authenticated_fetch: true,
              display_strategy: 'authenticated_file_fetch',
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        );
      })
      .mockImplementationOnce((url: string, init?: RequestInit) => {
        expect(String(url)).toContain('/file');
        expect(init).toEqual(expect.objectContaining({ credentials: 'omit' }));
        expect((init?.headers as Headers).get('Authorization')).toBe('Bearer tok');
        return Promise.resolve(
          new Response(new Blob(['x'], { type: 'image/jpeg' }), {
            status: 200,
            headers: { 'Content-Type': 'image/jpeg' },
          })
        );
      });
    vi.stubGlobal('fetch', fetchMock);
    const result = await fetchEvidenceImageDisplay(SPEC);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.imageSrc).toBe('blob:test-mock-url');
      expect(result.revoke).toBeDefined();
      result.revoke?.();
    }
  });

  it('returns not_found when image-display-url returns 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Asset not found' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    const result = await fetchEvidenceImageDisplay(SPEC);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.detail).toBe('Asset not found');
    }
  });

  it('returns forbidden when image-display-url returns 403', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Forbidden' }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    const result = await fetchEvidenceImageDisplay(SPEC);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(403);
    }
  });

  it('returns status 0 on network error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))));
    const result = await fetchEvidenceImageDisplay(SPEC);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(0);
    }
  });
});

function TestWrapper({ spec }: { spec: Parameters<typeof useEvidenceImageLoad>[0] }) {
  const state = useEvidenceImageLoad(spec);
  if (state.status === 'idle') return <span data-testid="state">idle</span>;
  if (state.status === 'loading') return <span data-testid="state">loading</span>;
  if (state.status === 'loaded') return <span data-testid="state">loaded</span>;
  return (
    <span data-testid="state" data-error-kind={state.kind}>
      {state.message}
    </span>
  );
}

describe('useEvidenceImageLoad', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    ensureBlobUrlSupport();
    vi.mocked(authStorage.getStoredToken).mockReturnValue(null);
  });

  const spec = { inventoryId: 'inv', aisleId: 'aisle', assetId: 'asset' };

  it('shows not_found message when image-display-url returns 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Asset not found' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    render(<TestWrapper spec={spec} />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('Source image unavailable');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('not_found');
  });

  it('shows forbidden message when image-display-url returns 403', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Forbidden' }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    render(<TestWrapper spec={spec} />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('Not allowed to view this image');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('forbidden');
  });

  it('shows generic message on network error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))));
    render(<TestWrapper spec={spec} />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('Network error loading image');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('network');
  });

  it('shows loaded when JSON returns presigned URL', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              image_url: 'https://signed.example/x',
              requires_authenticated_fetch: false,
              display_strategy: 'presigned_url',
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        )
      )
    );
    render(<TestWrapper spec={spec} />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('loaded');
    });
  });

  it('shows loaded when JSON requests fetch and /file returns 200', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              image_url: null,
              requires_authenticated_fetch: true,
              display_strategy: 'authenticated_file_fetch',
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        )
      )
      .mockImplementationOnce(() =>
        Promise.resolve(new Response(new Blob(['x'], { type: 'image/jpeg' }), { status: 200 }))
      );
    vi.stubGlobal('fetch', fetchMock);
    render(<TestWrapper spec={spec} />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('loaded');
    });
  });

  it('shows heic_preview_unavailable when 404 detail matches preview message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Preview is not available for this image' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    render(<TestWrapper spec={spec} />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('Preview unavailable');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('heic_preview_unavailable');
  });
});
