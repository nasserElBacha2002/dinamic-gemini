import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { ApiError } from '../api/types';
import type { InventoryVisualReference } from '../api/types';
import { fetchInventoryVisualReferenceFile } from '../api/client';
import { formatDate } from '../utils/formatDate';
import { getApiErrorMessage } from '../utils/apiErrors';
import { EmptyState, ErrorAlert, LoadingBlock, ImageAssetCard, ImagePreviewDialog } from './ui';

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 1024) return `${Math.max(0, Math.round(bytes || 0))} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
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
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const replaceInputRef = useRef<HTMLInputElement | null>(null);
  const previewRevokeRef = useRef<(() => void) | null>(null);
  const previewRequestIdRef = useRef(0);
  const mountedRef = useRef(true);
  const [previewTarget, setPreviewTarget] = useState<InventoryVisualReference | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InventoryVisualReference | null>(null);
  const [replaceTarget, setReplaceTarget] = useState<InventoryVisualReference | null>(null);
  const [replacingReferenceId, setReplacingReferenceId] = useState<string | null>(null);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (previewRevokeRef.current) {
        previewRevokeRef.current();
        previewRevokeRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!open) {
      clearPreview();
    }
  }, [open]);

  const clearPreview = () => {
    previewRequestIdRef.current += 1;
    if (previewRevokeRef.current) {
      previewRevokeRef.current();
      previewRevokeRef.current = null;
    }
    setPreviewTarget(null);
    setPreviewSrc(null);
    setPreviewLoading(false);
    setPreviewError(null);
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleReplaceClick = (item: InventoryVisualReference) => {
    setReplaceTarget(item);
    replaceInputRef.current?.click();
  };

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files ? Array.from(event.target.files) : [];
    event.target.value = '';
    if (files.length === 0) return;
    try {
      await onUpload(files);
    } catch {
      // Upload errors are surfaced by the parent mutation state via `uploadError`.
    }
  };

  const handleReplaceFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const target = replaceTarget;
    const file = event.target.files?.[0] ?? null;
    event.target.value = '';
    setReplaceTarget(null);
    if (!target || !file) return;
    setReplacingReferenceId(target.id);
    try {
      await onReplace(target.id, file);
    } catch {
      // Replace errors are surfaced by the parent mutation state via `replaceError`.
    } finally {
      setReplacingReferenceId(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await onDelete(deleteTarget.id);
      setDeleteTarget(null);
    } catch {
      // Delete errors are surfaced by the parent mutation state via `deleteError`.
    }
  };

  const handlePreview = async (item: InventoryVisualReference) => {
    clearPreview();
    const requestId = previewRequestIdRef.current;
    setPreviewTarget(item);
    setPreviewLoading(true);
    try {
      const result = await fetchInventoryVisualReferenceFile(inventoryId, item.id);
      if (!mountedRef.current || previewRequestIdRef.current !== requestId || !open) {
        result.revoke();
        return;
      }
      previewRevokeRef.current = result.revoke;
      setPreviewSrc(result.imageSrc);
    } catch (error) {
      if (!mountedRef.current || previewRequestIdRef.current !== requestId || !open) {
        return;
      }
      const apiError = error instanceof ApiError ? error : new ApiError(String(error));
      setPreviewError(getApiErrorMessage(apiError, 'Reference image preview could not be loaded'));
    } finally {
      if (mountedRef.current && previewRequestIdRef.current === requestId && open) {
        setPreviewLoading(false);
      }
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 'min(720px, 96vw)', lg: 'min(840px, 88vw)' },
          maxWidth: '100vw',
          display: 'flex',
          flexDirection: 'column',
          p: 0,
        },
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, bgcolor: 'background.paper' }}>
        <Box
          sx={{
            flexShrink: 0,
            position: 'sticky',
            top: 0,
            zIndex: 1,
            bgcolor: 'background.paper',
            borderBottom: 1,
            borderColor: 'divider',
            px: 2.5,
            py: 1.5,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 1,
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5 }}>
              Inventory
            </Typography>
            <Typography component="h2" variant="h6" sx={{ fontWeight: 600, lineHeight: 1.2, mt: 0.25 }}>
              Reference images
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
              Manage inventory-level references used as comparative context for future processing runs.
            </Typography>
          </Box>
          <IconButton aria-label="Close reference images drawer" onClick={onClose} size="small" edge="end">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, px: 2.5, py: 2 }}>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/jpg,image/png,image/webp"
            multiple
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
          <input
            ref={replaceInputRef}
            type="file"
            accept="image/jpeg,image/jpg,image/png,image/webp"
            style={{ display: 'none' }}
            onChange={handleReplaceFileChange}
          />
          {isLoading ? <LoadingBlock /> : null}

          {!isLoading && errorMessage ? <ErrorAlert message={errorMessage} onRetry={onRetry} /> : null}

          {!isLoading && !errorMessage ? (
            <Box sx={{ display: 'grid', gap: 2 }}>
              <Box
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                  p: 2,
                  display: 'grid',
                  gap: 1,
                }}
              >
                <Typography variant="subtitle2">Management</Typography>
                <Typography variant="body2" color="text.secondary">
                  Reference images belong to this inventory and are used for future processing runs only. Updating them
                  does not modify existing results automatically.
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  <Button
                    variant="contained"
                    size="small"
                    onClick={handleUploadClick}
                    disabled={isUploading || isDeleting || isReplacing}
                  >
                    {isUploading ? 'Uploading…' : 'Upload references'}
                  </Button>
                </Box>
                {uploadError ? <ErrorAlert message={uploadError} /> : null}
                {replaceError ? <ErrorAlert message={replaceError} /> : null}
                {deleteError ? <ErrorAlert message={deleteError} /> : null}
              </Box>

              {items.length === 0 ? (
                <EmptyState
                  title="No reference images uploaded yet"
                  message="Upload 1-3 images to help the analysis use expected pallet, label, or packaging references for this inventory."
                />
              ) : (
                <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
                  {items.map((item, index) => (
                    <Box key={item.id}>
                      {index > 0 ? <Divider /> : null}
                      <ImageAssetCard
                        title={item.filename}
                        subtitle={`${item.mime_type} \u2022 ${formatFileSize(item.file_size)} \u2022 Uploaded ${formatDate(
                          item.created_at
                        )}`}
                        actions={
                          <>
                            <Button variant="outlined" size="small" onClick={() => void handlePreview(item)}>
                              Preview
                            </Button>
                            <Button
                              variant="outlined"
                              size="small"
                              onClick={() => handleReplaceClick(item)}
                              disabled={isUploading || isDeleting || isReplacing}
                            >
                              {isReplacing && replacingReferenceId === item.id ? 'Replacing…' : 'Replace'}
                            </Button>
                            <Button
                              variant="outlined"
                              color="error"
                              size="small"
                              onClick={() => setDeleteTarget(item)}
                              disabled={isUploading || isDeleting || isReplacing}
                            >
                              Delete
                            </Button>
                          </>
                        }
                      />
                    </Box>
                  ))}
                </Box>
              )}
            </Box>
          ) : null}
        </Box>
      </Box>

      <ImagePreviewDialog
        open={Boolean(previewTarget)}
        onClose={clearPreview}
        title={previewTarget?.filename ?? 'Reference image'}
        src={previewSrc}
        alt={previewTarget?.filename ?? 'Reference image preview'}
        loading={previewLoading}
        error={previewError}
      />

      <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete reference image</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete <strong>{deleteTarget?.filename ?? 'this reference image'}</strong>? This affects future processing
            runs only and does not modify existing results automatically.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)} disabled={isDeleting}>
            Cancel
          </Button>
          <Button color="error" variant="contained" onClick={() => void handleDeleteConfirm()} disabled={isDeleting}>
            {isDeleting ? 'Deleting…' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Drawer>
  );
}
