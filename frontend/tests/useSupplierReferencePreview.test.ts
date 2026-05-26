import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSupplierReferencePreview } from '../src/features/clients/hooks/useSupplierReferencePreview';
import type { ManagedImageAssetItem } from '../src/components/imageAssets/types';

const item: ManagedImageAssetItem = {
  id: 'img-1',
  filename: 'ref.jpg',
  mime_type: 'image/jpeg',
  file_size: 100,
  created_at: '2024-01-01T00:00:00Z',
};

describe('useSupplierReferencePreview', () => {
  it('returns presigned GCS URL for direct img src without blob fetch', async () => {
    const gcsUrl =
      'https://storage.googleapis.com/bucket/v3/client_suppliers/s/ref.jpg?sig=1';
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      imageSrc: gcsUrl,
    });

    const { result } = renderHook(() =>
      useSupplierReferencePreview({
        clientId: 'c1',
        supplierId: 's1',
        fetchSupplierReferenceImageDisplayFn: fetchFn,
      })
    );

    const preview = await result.current.loadPreview(item);
    expect(fetchFn).toHaveBeenCalledWith('c1', 's1', 'img-1');
    expect(preview.imageSrc).toBe(gcsUrl);
    expect(preview.imageSrc.startsWith('blob:')).toBe(false);
  });

  it('supports authenticated blob preview when display endpoint requires fetch', async () => {
    const revoke = vi.fn();
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      imageSrc: 'blob:local-preview',
      revoke,
    });

    const { result } = renderHook(() =>
      useSupplierReferencePreview({
        clientId: 'c1',
        supplierId: 's1',
        fetchSupplierReferenceImageDisplayFn: fetchFn,
      })
    );

    const preview = await result.current.loadPreview(item);
    await waitFor(() => {
      expect(preview.imageSrc).toBe('blob:local-preview');
    });
    expect(preview.revoke).toBe(revoke);
  });
});
