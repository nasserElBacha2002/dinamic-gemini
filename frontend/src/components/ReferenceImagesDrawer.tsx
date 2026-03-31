import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { ApiError } from '../api/types';
import type { InventoryVisualReference } from '../api/types';
import { fetchInventoryVisualReferenceFile } from '../api/client';
import { formatDate } from '../utils/formatDate';
import { getApiErrorMessage } from '../utils/apiErrors';
import { EmptyState, ErrorAlert, LoadingBlock } from './ui';

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
}: ReferenceImagesDrawerProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const previewRevokeRef = useRef<(() => void) | null>(null);
  const previewRequestIdRef = useRef(0);
  const mountedRef = useRef(true);
  const [previewTarget, setPreviewTarget] = useState<InventoryVisualReference | null>(null);
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
                  <Button variant="contained" size="small" onClick={handleUploadClick} disabled={isUploading}>
                    {isUploading ? 'Uploading…' : 'Upload references'}
                  </Button>
                </Box>
                {uploadError ? <ErrorAlert message={uploadError} /> : null}
                <Typography variant="caption" color="text.secondary">
                  Replace and delete actions are not exposed yet because dedicated backend routes are not available in
                  the current contract.
                </Typography>
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
                      <Box
                        sx={{
                          px: 2.5,
                          py: 2,
                          display: 'grid',
                          gap: 1.25,
                        }}
                      >
                        <Box
                          sx={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            justifyContent: 'space-between',
                            gap: 2,
                            minWidth: 0,
                            flexWrap: { xs: 'wrap', sm: 'nowrap' },
                          }}
                        >
                          <Box sx={{ minWidth: 0, flex: 1 }}>
                            <Tooltip title={item.filename} placement="top-start">
                              <Typography
                                variant="subtitle2"
                                noWrap
                                sx={{ maxWidth: '100%', textOverflow: 'ellipsis', overflow: 'hidden' }}
                              >
                                {item.filename}
                              </Typography>
                            </Tooltip>
                          </Box>
                          <Box sx={{ flexShrink: 0 }}>
                            <Button variant="outlined" size="small" onClick={() => void handlePreview(item)}>
                              Preview
                            </Button>
                          </Box>
                        </Box>

                        <Typography variant="body2" color="text.secondary">
                          {item.mime_type} {'\u2022'} {formatFileSize(item.file_size)} {'\u2022'} Uploaded{' '}
                          {formatDate(item.created_at)}
                        </Typography>
                      </Box>
                    </Box>
                  ))}
                </Box>
              )}
            </Box>
          ) : null}
        </Box>
      </Box>

      <Dialog open={Boolean(previewTarget)} onClose={clearPreview} maxWidth="md" fullWidth>
        <DialogTitle>{previewTarget?.filename ?? 'Reference image'}</DialogTitle>
        <DialogContent>
          {previewLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress aria-label="Loading reference image preview" />
            </Box>
          ) : null}
          {!previewLoading && previewError ? <ErrorAlert message={previewError} onClose={() => setPreviewError(null)} /> : null}
          {!previewLoading && !previewError && previewSrc ? (
            <Box
              component="img"
              src={previewSrc}
              alt={previewTarget?.filename ?? 'Reference image preview'}
              sx={{ width: '100%', height: 'auto', display: 'block', borderRadius: 1 }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </Drawer>
  );
}
