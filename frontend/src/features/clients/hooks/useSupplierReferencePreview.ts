import { useCallback } from 'react';
import { fetchSupplierReferenceImageFile } from '../../../api/client';
import type { ManagedImageAssetItem } from '../../../components/imageAssets/types';

export interface UseSupplierReferencePreviewOptions {
  clientId: string;
  supplierId: string;
  fetchSupplierReferenceImageFileFn?: typeof fetchSupplierReferenceImageFile;
}

export function useSupplierReferencePreview({
  clientId,
  supplierId,
  fetchSupplierReferenceImageFileFn,
}: UseSupplierReferencePreviewOptions) {
  const loadPreview = useCallback(
    async (item: ManagedImageAssetItem) => {
      const fn = fetchSupplierReferenceImageFileFn ?? fetchSupplierReferenceImageFile;
      return fn(clientId, supplierId, item.id);
    },
    [clientId, supplierId, fetchSupplierReferenceImageFileFn]
  );

  return { loadPreview };
}
