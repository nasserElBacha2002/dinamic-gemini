import { useCallback, useState, type ReactNode } from 'react';
import ReferenceImagesDrawer from '../../../components/ReferenceImagesDrawer';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import {
  useInventoryVisualReferences,
  useUploadInventoryVisualReferences,
  useDeleteInventoryVisualReference,
  useReplaceInventoryVisualReference,
} from '../../../hooks';

export interface InventoryReferenceImagesRenderProps {
  openReferenceImages: () => void;
}

export interface InventoryReferenceImagesModuleProps {
  inventoryId: string;
  /** Mirrors lazy fetch: only fetch when drawer is open and inventory context is ready. */
  inventoryReady: boolean;
  children: (api: InventoryReferenceImagesRenderProps) => ReactNode;
}

/**
 * Owns visual reference query (lazy), drawer state, and upload/delete/replace mutations.
 * Renders as a fragment: children for composition (e.g. header button) + drawer.
 */
export default function InventoryReferenceImagesModule({
  inventoryId,
  inventoryReady,
  children,
}: InventoryReferenceImagesModuleProps) {
  const [open, setOpen] = useState(false);

  const visualReferencesQuery = useInventoryVisualReferences(inventoryId, {
    enabled: Boolean(open && inventoryId && inventoryReady),
  });

  const uploadMutation = useUploadInventoryVisualReferences(inventoryId);
  const deleteMutation = useDeleteInventoryVisualReference(inventoryId);
  const replaceMutation = useReplaceInventoryVisualReference(inventoryId);

  const handleClose = useCallback(() => {
    setOpen(false);
    uploadMutation.reset();
    deleteMutation.reset();
    replaceMutation.reset();
  }, [deleteMutation, replaceMutation, uploadMutation]);

  const visualReferencesError =
    visualReferencesQuery.isError && visualReferencesQuery.error
      ? resolveApiErrorMessage(visualReferencesQuery.error, 'errors.load_reference_images')
      : null;

  const openReferenceImages = useCallback(() => setOpen(true), []);

  return (
    <>
      {children({ openReferenceImages })}
      <ReferenceImagesDrawer
        inventoryId={inventoryId}
        open={open}
        onClose={handleClose}
        items={visualReferencesQuery.data?.items ?? []}
        isLoading={visualReferencesQuery.isLoading}
        errorMessage={visualReferencesError}
        onRetry={() => visualReferencesQuery.refetch()}
        onUpload={(files) => uploadMutation.mutateAsync(files)}
        isUploading={uploadMutation.isPending}
        uploadError={
          uploadMutation.isError && uploadMutation.error
            ? resolveApiErrorMessage(uploadMutation.error, 'errors.upload_reference_images')
            : null
        }
        onDelete={(referenceId) => deleteMutation.mutateAsync(referenceId)}
        isDeleting={deleteMutation.isPending}
        deleteError={
          deleteMutation.isError && deleteMutation.error
            ? resolveApiErrorMessage(deleteMutation.error, 'errors.delete_reference_image')
            : null
        }
        onReplace={(referenceId, file) => replaceMutation.mutateAsync({ referenceId, file })}
        isReplacing={replaceMutation.isPending}
        replaceError={
          replaceMutation.isError && replaceMutation.error
            ? resolveApiErrorMessage(replaceMutation.error, 'errors.replace_reference_image')
            : null
        }
      />
    </>
  );
}
