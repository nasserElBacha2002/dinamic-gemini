import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, TextField, Typography } from '@mui/material';
import type { SupplierReferenceImage } from '../../../api/types';
import ManagedImageAssetsDrawer from '../../../components/imageAssets/ManagedImageAssetsDrawer';
import type { ManagedImageAssetItem } from '../../../components/imageAssets/types';
import { formatDate } from '../../../utils/formatDate';
import { useSupplierReferencePreview } from '../hooks/useSupplierReferencePreview';
import SupplierReferenceAnnotationEditorDialog from './SupplierReferenceAnnotationEditorDialog';

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

export interface SupplierReferenceImagesDrawerProps {
  clientId: string;
  supplierId: string;
  supplierName: string;
  open: boolean;
  embedded?: boolean;
  onClose: () => void;
  items: SupplierReferenceImage[];
  isLoading: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  onUpload: (payload: {
    files: File[];
    label?: string;
    description?: string;
  }) => Promise<unknown>;
  isUploading?: boolean;
  uploadError?: string | null;
  onDelete: (imageId: string) => Promise<unknown>;
  isDeleting?: boolean;
  deleteError?: string | null;
  activeExtractionProfileId?: string | null;
  annotationsEnabled?: boolean;
}

export default function SupplierReferenceImagesDrawer({
  clientId,
  supplierId,
  supplierName,
  open,
  embedded = false,
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
  activeExtractionProfileId = null,
  annotationsEnabled = false,
}: SupplierReferenceImagesDrawerProps) {
  const { t } = useTranslation();
  const { loadPreview } = useSupplierReferencePreview({ clientId, supplierId });
  const [label, setLabel] = useState('');
  const [description, setDescription] = useState('');
  const [annotationTarget, setAnnotationTarget] = useState<ManagedImageAssetItem | null>(null);
  const managedItems = useMemo(() => toManagedItems(items), [items]);

  const copy = useMemo(
    () => ({
      closeAria: t('clients.suppliers.reference_images.close'),
      contextOverline: t('clients.suppliers.reference_images.context_overline'),
      title: t('clients.suppliers.reference_images.title'),
      subtitle: t('clients.suppliers.reference_images.subtitle', { name: supplierName }),
      managementTitle: t('clients.suppliers.reference_images.management_title'),
      managementBody: t('clients.suppliers.reference_images.management_body'),
      uploadButton: t('clients.suppliers.reference_images.upload'),
      emptyTitle: t('clients.suppliers.reference_images.empty_title'),
      emptyMessage: t('clients.suppliers.reference_images.empty_description'),
      preview: t('clients.suppliers.reference_images.preview'),
      delete: t('clients.suppliers.reference_images.delete'),
      deleteTitle: t('clients.suppliers.reference_images.delete_confirm_title'),
      deleteFallbackName: t('clients.suppliers.reference_images.delete_fallback_name'),
      imagePreviewTitle: t('clients.suppliers.reference_images.image_preview_title'),
      imagePreviewAlt: t('clients.suppliers.reference_images.image_preview_alt'),
    }),
    [supplierName, t]
  );

  const uploadExtras = (
    <Box sx={{ display: 'grid', gap: 1.5, pt: 0.5 }}>
      <Typography variant="caption" color="text.secondary">
        {t('clients.suppliers.reference_images.optional_metadata_hint')}
      </Typography>
      <TextField
        label={t('clients.suppliers.reference_images.label')}
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        size="small"
        fullWidth
        disabled={isUploading}
      />
      <TextField
        label={t('clients.suppliers.reference_images.description')}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        size="small"
        fullWidth
        multiline
        minRows={2}
        disabled={isUploading}
      />
    </Box>
  );

  return (
    <>
      <ManagedImageAssetsDrawer
        open={embedded ? true : open}
        embedded={embedded}
        onClose={onClose}
        copy={copy}
        items={managedItems}
        getItemSubtitle={(item) =>
          t('clients.suppliers.reference_images.subtitle_uploaded', {
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
        uploadMultiple={false}
        uploadExtras={uploadExtras}
        onUpload={async (files) => {
          const trimmedLabel = label.trim();
          const trimmedDesc = description.trim();
          await onUpload({
            files,
            label: trimmedLabel || undefined,
            description: trimmedDesc || undefined,
          });
          setLabel('');
          setDescription('');
        }}
        isUploading={isUploading}
        uploadError={uploadError}
        showReplace={false}
        onDelete={onDelete}
        isDeleting={isDeleting}
        deleteError={deleteError}
        formatDeleteConfirm={(name) =>
          t('clients.suppliers.reference_images.delete_confirm_body', { name })
        }
        renderItemExtraActions={
          annotationsEnabled
            ? (item) => (
                <Button variant="outlined" size="small" onClick={() => setAnnotationTarget(item)}>
                  {t('clients.extraction_profile.annotations.configure_fields')}
                </Button>
              )
            : undefined
        }
      />
      {annotationTarget ? (
        <SupplierReferenceAnnotationEditorDialog
          open
          onClose={() => setAnnotationTarget(null)}
          clientId={clientId}
          supplierId={supplierId}
          imageId={annotationTarget.id}
          imageLabel={annotationTarget.filename}
          activeProfileId={activeExtractionProfileId}
        />
      ) : null}
    </>
  );
}
