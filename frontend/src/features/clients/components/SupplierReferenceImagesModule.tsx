import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppSnackbar } from '../../../components/ui';
import {
  useDeleteSupplierReferenceImage,
  useActiveSupplierExtractionProfile,
  useSupplierReferenceImages,
  useUploadSupplierReferenceImages,
} from '../../../hooks';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import SupplierReferenceImagesDrawer, {
  type SupplierReferenceImagesDrawerProps,
} from './SupplierReferenceImagesDrawer';

export interface SupplierReferenceImagesModuleProps {
  clientId: string;
  supplierId: string;
  supplierName: string;
  open: boolean;
  onClose: () => void;
  presentation?: 'drawer' | 'inline';
}

/**
 * Lazy-fetches supplier reference images when the drawer is open; upload/delete invalidate scoped query.
 */
export default function SupplierReferenceImagesModule({
  clientId,
  supplierId,
  supplierName,
  open,
  onClose,
  presentation = 'drawer',
}: SupplierReferenceImagesModuleProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const moduleActive = presentation === 'inline' || open;
  const embedded = presentation === 'inline';
  const imagesQuery = useSupplierReferenceImages(clientId, supplierId, {
    enabled: Boolean(moduleActive && clientId && supplierId),
  });
  const activeProfileQuery = useActiveSupplierExtractionProfile(clientId, supplierId, {
    enabled: Boolean(moduleActive && clientId && supplierId),
  });
  const activeExtractionProfileId =
    activeProfileQuery.data?.id ??
    (activeProfileQuery.isError &&
    activeProfileQuery.error instanceof ApiError &&
    activeProfileQuery.error.status === 404
      ? null
      : undefined);
  const uploadMutation = useUploadSupplierReferenceImages(clientId, supplierId);
  const deleteMutation = useDeleteSupplierReferenceImage(clientId, supplierId);

  const handleClose = useCallback(() => {
    onClose();
    uploadMutation.reset();
    deleteMutation.reset();
  }, [deleteMutation, onClose, uploadMutation]);

  const errorMessage =
    imagesQuery.isError && imagesQuery.error
      ? resolveApiErrorMessage(imagesQuery.error, 'clients.suppliers.reference_images.load_error')
      : null;

  const handleUpload = useCallback(
    async (payload: Parameters<SupplierReferenceImagesDrawerProps['onUpload']>[0]) => {
      await uploadMutation.mutateAsync(payload);
      showSnackbar(t('clients.suppliers.reference_images.upload_success'), 'success');
    },
    [showSnackbar, t, uploadMutation]
  );

  const handleDelete = useCallback(
    async (imageId: string) => {
      try {
        await deleteMutation.mutateAsync(imageId);
        showSnackbar(t('clients.suppliers.reference_images.delete_success'), 'success');
      } catch {
        /* Drawer surfaces deleteMutation error */
      }
    },
    [deleteMutation, showSnackbar, t]
  );

  return (
    <SupplierReferenceImagesDrawer
      clientId={clientId}
      supplierId={supplierId}
      supplierName={supplierName}
      open={embedded ? true : open}
      embedded={embedded}
      onClose={handleClose}
      items={imagesQuery.data?.items ?? []}
      isLoading={imagesQuery.isLoading}
      errorMessage={errorMessage}
      onRetry={() => imagesQuery.refetch()}
      onUpload={handleUpload}
      isUploading={uploadMutation.isPending}
      uploadError={
        uploadMutation.isError && uploadMutation.error
          ? resolveApiErrorMessage(uploadMutation.error, 'clients.suppliers.reference_images.upload_error')
          : null
      }
      onDelete={handleDelete}
      isDeleting={deleteMutation.isPending}
      deleteError={
        deleteMutation.isError && deleteMutation.error
          ? resolveApiErrorMessage(deleteMutation.error, 'clients.suppliers.reference_images.delete_error')
          : null
      }
      activeExtractionProfileId={activeExtractionProfileId ?? null}
    />
  );
}
