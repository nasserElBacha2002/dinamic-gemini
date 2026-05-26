import { useCallback } from 'react';
import { fetchSupplierReferenceImageDisplay } from '../../../api/client';
import type { ManagedImageAssetItem } from '../../../components/imageAssets/types';

export interface UseSupplierReferencePreviewOptions {
  clientId: string;
  supplierId: string;
  fetchSupplierReferenceImageDisplayFn?: typeof fetchSupplierReferenceImageDisplay;
}

export function useSupplierReferencePreview({
  clientId,
  supplierId,
  fetchSupplierReferenceImageDisplayFn,
}: UseSupplierReferencePreviewOptions) {
  const loadPreview = useCallback(
    async (item: ManagedImageAssetItem) => {
      const fn = fetchSupplierReferenceImageDisplayFn ?? fetchSupplierReferenceImageDisplay;
      const result = await fn(clientId, supplierId, item.id);
      if (!result.ok) {
        throw new Error(result.detail ?? 'Preview failed');
      }
      return { imageSrc: result.imageSrc, revoke: result.revoke };
    },
    [clientId, supplierId, fetchSupplierReferenceImageDisplayFn]
  );

  return { loadPreview };
}
