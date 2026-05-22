import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { fetchEvidenceImageDisplay } from '../../../api/client';
import type { SourceAssetSummary } from '../../../api/types';
import { ApiError } from '../../../api/types';
import ManagedImageAssetsDrawer from '../../../components/imageAssets/ManagedImageAssetsDrawer';
import type { ManagedImageAssetItem } from '../../../components/imageAssets/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { formatDate } from '../../../utils/formatDate';
import {
  useAisleSourceAssets,
  useDeleteAisleSourceAsset,
  useUploadAisleAssets,
} from '../../../hooks';

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 1024) return `${Math.max(0, Math.round(bytes || 0))} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function toManagedItems(rows: SourceAssetSummary[]): ManagedImageAssetItem[] {
  return rows.map((s) => ({
    id: s.id,
    filename: s.original_filename,
    mime_type: s.mime_type,
    file_size: s.file_size_bytes ?? 0,
    created_at: s.uploaded_at,
  }));
}

export interface AisleSourceAssetsManageModuleProps {
  inventoryId: string;
  aisleId: string;
  /** Shown as drawer context line (e.g. inventory name). */
  inventoryLabel: string;
  /** Optional job id for HEIC / normalized preview resolution (same as evidence viewer). */
  jobIdForPreview?: string | null;
  /** Gate lazy fetch until inventory context is ready. */
  inventoryReady: boolean;
  children: (ctx: { openSourceAssets: () => void }) => ReactNode;
}

export default function AisleSourceAssetsManageModule({
  inventoryId,
  aisleId,
  inventoryLabel,
  jobIdForPreview,
  inventoryReady,
  children,
}: AisleSourceAssetsManageModuleProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const assetsQuery = useAisleSourceAssets(inventoryId, aisleId, {
    enabled: Boolean(open && inventoryId && aisleId && inventoryReady),
  });
  const uploadMutation = useUploadAisleAssets(inventoryId, aisleId);
  const deleteMutation = useDeleteAisleSourceAsset(inventoryId, aisleId);

  const handleClose = useCallback(() => {
    if (uploadMutation.isPending) return;
    setOpen(false);
    uploadMutation.reset();
    deleteMutation.reset();
  }, [deleteMutation, uploadMutation]);

  const openSourceAssets = useCallback(() => setOpen(true), []);

  const loadError =
    assetsQuery.isError && assetsQuery.error
      ? resolveApiErrorMessage(assetsQuery.error, 'errors.load_aisle_source_assets')
      : null;

  const items = useMemo(
    () => toManagedItems(assetsQuery.data ?? []),
    [assetsQuery.data]
  );

  const copy = useMemo(
    () => ({
      closeAria: t('aisle_source_assets.close'),
      contextOverline: inventoryLabel,
      title: t('aisle_source_assets.drawer_title'),
      subtitle: t('aisle_source_assets.drawer_subtitle'),
      managementTitle: t('aisle_source_assets.management_title'),
      managementBody: t('aisle_source_assets.management_body'),
      uploadButton: t('aisle_source_assets.upload_button'),
      emptyTitle: t('aisle_source_assets.empty_title'),
      emptyMessage: t('aisle_source_assets.empty_message'),
      preview: t('common.preview'),
      delete: t('common.delete'),
      deleteTitle: t('aisle_source_assets.delete_title'),
      deleteFallbackName: t('aisle_source_assets.delete_fallback_name'),
      imagePreviewTitle: t('aisle_source_assets.image_preview_title'),
      imagePreviewAlt: t('aisle_source_assets.image_preview_alt'),
    }),
    [inventoryLabel, t]
  );

  const onFetchPreview = useCallback(
    async (item: ManagedImageAssetItem) => {
      const res = await fetchEvidenceImageDisplay({
        inventoryId,
        aisleId,
        assetId: item.id,
        jobId: jobIdForPreview ?? null,
      });
      if (!res.ok) {
        throw new ApiError(
          res.detail ?? t('errors.preview_aisle_asset_failed'),
          res.status,
          res.detail ? { detail: res.detail } : undefined
        );
      }
      return { imageSrc: res.imageSrc, revoke: res.revoke };
    },
    [aisleId, inventoryId, jobIdForPreview, t]
  );

  return (
    <>
      {children({ openSourceAssets })}
      <ManagedImageAssetsDrawer
        open={open}
        onClose={handleClose}
        copy={copy}
        items={items}
        getItemSubtitle={(item) => {
          const sizeLabel = formatFileSize(item.file_size);
          if (item.created_at) {
            return t('aisle_source_assets.card_subtitle_with_date', {
              mime: item.mime_type,
              size: sizeLabel,
              date: formatDate(item.created_at),
            });
          }
          return t('aisle_source_assets.card_subtitle_no_date', {
            mime: item.mime_type,
            size: sizeLabel,
          });
        }}
        isLoading={assetsQuery.isLoading}
        errorMessage={loadError}
        onRetry={() => void assetsQuery.refetch()}
        onFetchPreview={onFetchPreview}
        showUpload
        onUpload={(files) => uploadMutation.mutateAsync(files)}
        isUploading={uploadMutation.isPending}
        uploadError={
          uploadMutation.isError && uploadMutation.error
            ? resolveApiErrorMessage(uploadMutation.error, 'errors.upload_aisle_source_assets')
            : null
        }
        uploadAccept="image/jpeg,image/jpg,image/png,image/webp,image/heic,image/heif"
        previewBlockedMessage={(item) =>
          item.mime_type.toLowerCase().startsWith('video/')
            ? t('errors.preview_aisle_video_not_supported')
            : null
        }
        onDelete={(id) => deleteMutation.mutateAsync(id)}
        isDeleting={deleteMutation.isPending}
        deleteError={
          deleteMutation.isError && deleteMutation.error
            ? resolveApiErrorMessage(deleteMutation.error, 'errors.delete_aisle_source_asset')
            : null
        }
        formatDeleteConfirm={(name) =>
          name === copy.deleteFallbackName
            ? t('aisle_source_assets.delete_confirm_anonymous')
            : t('aisle_source_assets.delete_confirm_named', { fileName: name })
        }
        previewErrorMessageKey="errors.preview_aisle_asset_failed"
      />
    </>
  );
}
