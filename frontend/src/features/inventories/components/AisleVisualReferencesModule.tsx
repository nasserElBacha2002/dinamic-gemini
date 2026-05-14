import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Aisle, SupplierReferenceImage } from '../../../api/types';
import ManagedImageAssetsDrawer from '../../../components/imageAssets/ManagedImageAssetsDrawer';
import type { ManagedImageAssetItem } from '../../../components/imageAssets/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { formatDate } from '../../../utils/formatDate';
import { useSupplierReferenceImages } from '../../../hooks';
import { pickSupplierReferenceImagesForAisle } from '../adapters/aisleReferenceImages';
import { useSupplierReferencePreview } from '../../clients/hooks/useSupplierReferencePreview';

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 1024) return `${Math.max(0, Math.round(bytes || 0))} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function toManagedItems(items: SupplierReferenceImage[]): ManagedImageAssetItem[] {
  return items.map((r) => ({
    id: r.id,
    filename: r.filename,
    mime_type: r.mime_type,
    file_size: r.file_size,
    created_at: r.created_at,
  }));
}

/** Minimal aisle DTO for `pickSupplierReferenceImagesForAisle` when list data is still loading. */
const AISLE_FOR_PICK_FALLBACK: Aisle = {
  id: '',
  inventory_id: '',
  code: '',
  status: 'created',
  created_at: '',
  updated_at: '',
  latest_job: null,
};

export interface AisleVisualReferencesModuleProps {
  inventoryLabel: string;
  clientId: string | null | undefined;
  clientSupplierId: string | null | undefined;
  aisle: Aisle | null;
  inventoryReady: boolean;
  children: (ctx: {
    openVisualReferences: () => void;
    disabled: boolean;
    disabledTooltip: string | null;
  }) => ReactNode;
}

export default function AisleVisualReferencesModule({
  inventoryLabel,
  clientId,
  clientSupplierId,
  aisle,
  inventoryReady,
  children,
}: AisleVisualReferencesModuleProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const clientIdTrim = (clientId ?? '').trim();
  const supplierIdTrim = (clientSupplierId ?? '').trim();

  const disabledTooltip = useMemo(() => {
    if (!inventoryReady) return null;
    if (!clientIdTrim) return t('positions.visual_references.tooltip_no_client');
    if (!supplierIdTrim) return t('positions.visual_references.tooltip_no_supplier');
    return null;
  }, [clientIdTrim, inventoryReady, supplierIdTrim, t]);

  const disabled = Boolean(disabledTooltip);

  const imagesQuery = useSupplierReferenceImages(clientIdTrim || undefined, supplierIdTrim || undefined, {
    enabled: Boolean(open && clientIdTrim && supplierIdTrim && inventoryReady),
  });

  const { loadPreview } = useSupplierReferencePreview({
    clientId: clientIdTrim,
    supplierId: supplierIdTrim,
  });

  const handleClose = useCallback(() => setOpen(false), []);

  const openVisualReferences = useCallback(() => {
    if (disabled) return;
    setOpen(true);
  }, [disabled]);

  const pickedReferences = useMemo(() => {
    const catalog = imagesQuery.data?.items;
    return pickSupplierReferenceImagesForAisle(aisle ?? AISLE_FOR_PICK_FALLBACK, catalog);
  }, [aisle, imagesQuery.data?.items]);

  const items = useMemo(() => toManagedItems(pickedReferences), [pickedReferences]);

  const loadError =
    imagesQuery.isError && imagesQuery.error
      ? resolveApiErrorMessage(imagesQuery.error, 'errors.load_reference_images')
      : null;

  const copy = useMemo(
    () => ({
      closeAria: t('positions.visual_references.close'),
      contextOverline: inventoryLabel,
      title: t('positions.visual_references.drawer_title'),
      subtitle: t('positions.visual_references.drawer_subtitle_supplier'),
      managementTitle: '',
      managementBody: '',
      uploadButton: '',
      emptyTitle: t('positions.visual_references.empty_title'),
      emptyMessage: t('positions.visual_references.empty_message'),
      preview: t('aisle_source_assets.preview'),
      delete: '',
      deleteTitle: '',
      deleteFallbackName: '',
      imagePreviewTitle: t('clients.suppliers.reference_images.image_preview_title'),
      imagePreviewAlt: t('clients.suppliers.reference_images.image_preview_alt'),
    }),
    [inventoryLabel, t]
  );

  return (
    <>
      {children({ openVisualReferences, disabled, disabledTooltip })}
      <ManagedImageAssetsDrawer
        readOnly
        open={open}
        onClose={handleClose}
        copy={copy}
        items={items}
        getItemSubtitle={(item) =>
          t('clients.suppliers.reference_images.subtitle_uploaded', {
            mime: item.mime_type,
            size: formatFileSize(item.file_size),
            date: formatDate(item.created_at),
          })
        }
        isLoading={imagesQuery.isLoading}
        loadingMessage={t('positions.visual_references.loading')}
        errorMessage={loadError}
        onRetry={() => void imagesQuery.refetch()}
        onFetchPreview={loadPreview}
        showUpload={false}
        previewErrorMessageKey="errors.preview_reference_failed"
      />
    </>
  );
}
