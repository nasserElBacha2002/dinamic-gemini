import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { InventoryVisualReference } from '../api/types';
import { formatDate } from '../utils/formatDate';
import { useInventoryReferencePreview } from '../features/imageAssets/hooks/useInventoryReferencePreview';
import ManagedImageAssetsDrawer from './imageAssets/ManagedImageAssetsDrawer';
import type { ManagedImageAssetItem } from './imageAssets/types';

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 1024) return `${Math.max(0, Math.round(bytes || 0))} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function toManagedItems(items: InventoryVisualReference[]): ManagedImageAssetItem[] {
  return items.map((r) => ({
    id: r.id,
    filename: r.filename,
    mime_type: r.mime_type,
    file_size: r.file_size,
    created_at: r.created_at,
  }));
}

export interface ReferenceImagesDrawerProps {
  inventoryId: string;
  open: boolean;
  onClose: () => void;
  items: InventoryVisualReference[];
  isLoading: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  onUpload: (files: File[]) => Promise<unknown>;
  isUploading?: boolean;
  uploadError?: string | null;
  onDelete: (referenceId: string) => Promise<unknown>;
  isDeleting?: boolean;
  deleteError?: string | null;
  onReplace: (referenceId: string, file: File) => Promise<unknown>;
  isReplacing?: boolean;
  replaceError?: string | null;
}

export default function ReferenceImagesDrawer({
  inventoryId,
  open,
  onClose,
  items,
  isLoading,
  errorMessage,
  onRetry,
  onUpload,
  isUploading = false,
  uploadError,
  onDelete,
  isDeleting = false,
  deleteError,
  onReplace,
  isReplacing = false,
  replaceError,
}: ReferenceImagesDrawerProps) {
  const { t } = useTranslation();
  const { loadPreview } = useInventoryReferencePreview({ inventoryId });
  const managedItems = useMemo(() => toManagedItems(items), [items]);

  const copy = useMemo(
    () => ({
      closeAria: t('reference_drawer.close'),
      contextOverline: t('reference_drawer.inventory_label'),
      title: t('reference_drawer.drawer_title'),
      subtitle: t('reference_drawer.drawer_subtitle'),
      managementTitle: t('reference_drawer.management_title'),
      managementBody: t('reference_drawer.management_body'),
      uploadButton: t('reference_drawer.upload_references'),
      emptyTitle: t('reference_drawer.empty_title'),
      emptyMessage: t('reference_drawer.empty_message'),
      preview: t('reference_drawer.preview'),
      replace: t('reference_drawer.replace'),
      delete: t('reference_drawer.delete'),
      deleteTitle: t('reference_drawer.delete_title'),
      deleteFallbackName: t('reference_drawer.delete_fallback_name'),
      imagePreviewTitle: t('reference_drawer.image_preview_title'),
      imagePreviewAlt: t('reference_drawer.image_preview_alt'),
    }),
    [t]
  );

  return (
    <ManagedImageAssetsDrawer
      open={open}
      onClose={onClose}
      copy={copy}
      items={managedItems}
      getItemSubtitle={(item) =>
        t('reference_drawer.subtitle_uploaded', {
          mime: item.mime_type,
          size: formatFileSize(item.file_size),
          date: formatDate(item.created_at),
        })
      }
      isLoading={isLoading}
      errorMessage={errorMessage}
      onRetry={onRetry}
      onFetchPreview={loadPreview}
      showUpload
      onUpload={onUpload}
      isUploading={isUploading}
      uploadError={uploadError}
      showReplace
      onReplace={onReplace}
      isReplacing={isReplacing}
      replaceError={replaceError}
      onDelete={onDelete}
      isDeleting={isDeleting}
      deleteError={deleteError}
      formatDeleteConfirm={(name) =>
        t('reference_drawer.delete_confirm', {
          name,
        })
      }
    />
  );
}
