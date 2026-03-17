/**
 * Evidence image load — fetch preflight and differentiated error handling.
 * Ensures 404, 403, network and success are mapped to the right UI state/message.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { fetchEvidenceImage } from '../../src/api/client';
import { useEvidenceImageLoad } from '../../src/features/results/hooks/useEvidenceImageLoad';

// Node/jsdom may lack URL.createObjectURL/revokeObjectURL; add no-op mocks so tests run
function ensureBlobUrlSupport() {
  if (typeof (URL as unknown as { createObjectURL?: (b: Blob) => string }).createObjectURL !== 'function') {
    (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = vi.fn(() => 'blob:test-mock-url');
  }
  if (typeof (URL as unknown as { revokeObjectURL?: (u: string) => void }).revokeObjectURL !== 'function') {
    (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL = vi.fn();
  }
}

describe('fetchEvidenceImage', () => {
  beforeEach(() => {
    ensureBlobUrlSupport();
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: string) => Promise.reject(new Error('network error')))
    );
  });

  it('returns not_found when backend returns 404 with Asset not found', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string) =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Asset not found' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    const result = await fetchEvidenceImage('http://api/assets/1/file');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.detail).toBe('Asset not found');
    }
  });

  it('returns forbidden when backend returns 403', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string) =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Forbidden' }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    const result = await fetchEvidenceImage('http://api/assets/1/file');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(403);
    }
  });

  it('returns blobUrl when backend returns 200', async () => {
    const blob = new Blob(['fake-image'], { type: 'image/jpeg' });
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string) =>
        Promise.resolve(
          new Response(blob, {
            status: 200,
            headers: { 'Content-Type': 'image/jpeg' },
          })
        )
      )
    );
    const result = await fetchEvidenceImage('http://api/assets/1/file');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.blobUrl).toBe('blob:test-mock-url');
      URL.revokeObjectURL(result.blobUrl);
    }
  });

  it('returns status 0 and no detail on network error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))));
    const result = await fetchEvidenceImage('http://api/assets/1/file');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(0);
    }
  });
});

function TestWrapper({ url }: { url: string | null }) {
  const state = useEvidenceImageLoad(url);
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
  });

  it('shows not_found message when backend returns 404 Asset not found', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string) =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Asset not found' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    render(<TestWrapper url="http://api/assets/1/file" />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('Source image is no longer available.');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('not_found');
  });

  it('shows forbidden message when backend returns 403', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string) =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Forbidden' }), {
            status: 403,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    render(<TestWrapper url="http://api/assets/1/file" />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('You do not have permission to load this image.');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('forbidden');
  });

  it('shows generic message on network error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))));
    render(<TestWrapper url="http://api/assets/1/file" />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('Image could not be loaded.');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('network');
  });

  it('shows loaded when response is OK', async () => {
    const blob = new Blob(['x'], { type: 'image/jpeg' });
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string) =>
        Promise.resolve(new Response(blob, { status: 200, headers: { 'Content-Type': 'image/jpeg' } }))
      )
    );
    render(<TestWrapper url="http://api/assets/1/file" />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('loaded');
    });
  });

  it('shows heic_preview_unavailable when 404 detail contains Preview not available', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string) =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'Preview is not available for this image' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          })
        )
      )
    );
    render(<TestWrapper url="http://api/assets/1/file" />);
    await waitFor(() => {
      expect(screen.getByTestId('state').textContent).toBe('Preview is not available for this image.');
    });
    expect(screen.getByTestId('state').getAttribute('data-error-kind')).toBe('heic_preview_unavailable');
  });
});
