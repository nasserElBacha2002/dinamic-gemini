import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
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
import { getVisibleErrorMessage } from '../../utils/apiErrors';
import { EmptyState, ErrorAlert, LoadingBlock, ImageAssetCard, ImagePreviewDialog } from '../ui';
import type { ManagedImageAssetItem } from './types';

export interface ManagedImageAssetsDrawerCopy {
  closeAria: string;
  contextOverline: string;
  title: string;
  subtitle?: string | null;
  managementTitle: string;
  managementBody: string;
  uploadButton: string;
  emptyTitle: string;
  emptyMessage: string;
  preview: string;
  /** Required when ``showReplace`` is true. */
  replace?: string;
  delete: string;
  deleteTitle: string;
  deleteFallbackName: string;
  imagePreviewTitle: string;
  imagePreviewAlt: string;
}

export interface ManagedImageAssetsDrawerProps {
  open: boolean;
  onClose: () => void;
  copy: ManagedImageAssetsDrawerCopy;
  items: ManagedImageAssetItem[];
  getItemSubtitle: (item: ManagedImageAssetItem) => string;
  isLoading: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  onFetchPreview: (item: ManagedImageAssetItem) => Promise<{ imageSrc: string; revoke?: () => void }>;
  showUpload?: boolean;
  onUpload?: (files: File[]) => Promise<unknown>;
  isUploading?: boolean;
  uploadError?: string | null;
  /** e.g. image/* only or include video */
  uploadAccept?: string;
  showReplace?: boolean;
  onReplace?: (assetId: string, file: File) => Promise<unknown>;
  isReplacing?: boolean;
  replaceError?: string | null;
  onDelete: (assetId: string) => Promise<unknown>;
  isDeleting?: boolean;
  deleteError?: string | null;
  previewErrorMessageKey?: string;
  /** When this returns a non-empty string, preview is skipped and the message is shown (e.g. video in image-only viewer). */
  previewBlockedMessage?: (item: ManagedImageAssetItem) => string | null;
  formatDeleteConfirm: (fileName: string) => string;
}

export default function ManagedImageAssetsDrawer({
  open,
  onClose,
  copy,
  items,
  getItemSubtitle,
  isLoading,
  errorMessage,
  onRetry,
  onFetchPreview,
  showUpload = false,
  onUpload,
  isUploading = false,
  uploadError,
  uploadAccept = 'image/jpeg,image/jpg,image/png,image/webp',
  showReplace = false,
  onReplace,
  isReplacing = false,
  replaceError,
  onDelete,
  isDeleting = false,
  deleteError,
  previewErrorMessageKey = 'errors.preview_reference_failed',
  previewBlockedMessage,
  formatDeleteConfirm,
}: ManagedImageAssetsDrawerProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const replaceInputRef = useRef<HTMLInputElement | null>(null);
  const previewRevokeRef = useRef<(() => void) | null>(null);
  const previewRequestIdRef = useRef(0);
  const mountedRef = useRef(true);
  const [previewTarget, setPreviewTarget] = useState<ManagedImageAssetItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ManagedImageAssetItem | null>(null);
  const [replaceTarget, setReplaceTarget] = useState<ManagedImageAssetItem | null>(null);
  const [replacingAssetId, setReplacingAssetId] = useState<string | null>(null);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      previewRequestIdRef.current += 1;
      if (previewRevokeRef.current) {
        previewRevokeRef.current();
        previewRevokeRef.current = null;
      }
    };
  }, []);

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

  useEffect(() => {
    if (!open) {
      previewRequestIdRef.current += 1;
      if (previewRevokeRef.current) {
        previewRevokeRef.current();
        previewRevokeRef.current = null;
      }
    }
  }, [open]);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleReplaceClick = (item: ManagedImageAssetItem) => {
    setReplaceTarget(item);
    replaceInputRef.current?.click();
  };

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files ? Array.from(event.target.files) : [];
    event.target.value = '';
    if (files.length === 0 || !onUpload) return;
    try {
      await onUpload(files);
    } catch {
      /* surfaced via uploadError */
    }
  };

  const handleReplaceFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const target = replaceTarget;
    const file = event.target.files?.[0] ?? null;
    event.target.value = '';
    setReplaceTarget(null);
    if (!target || !file || !onReplace) return;
    setReplacingAssetId(target.id);
    try {
      await onReplace(target.id, file);
    } catch {
      /* surfaced via replaceError */
    } finally {
      setReplacingAssetId(null);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await onDelete(deleteTarget.id);
      setDeleteTarget(null);
    } catch {
      /* surfaced via deleteError */
    }
  };

  const handlePreview = async (item: ManagedImageAssetItem) => {
    const blocked = previewBlockedMessage?.(item)?.trim();
    if (blocked) {
      previewRequestIdRef.current += 1;
      if (previewRevokeRef.current) {
        previewRevokeRef.current();
        previewRevokeRef.current = null;
      }
      setPreviewTarget(item);
      setPreviewSrc(null);
      setPreviewLoading(false);
      setPreviewError(blocked);
      return;
    }
    clearPreview();
    const requestId = previewRequestIdRef.current;
    setPreviewTarget(item);
    setPreviewLoading(true);
    try {
      const result = await onFetchPreview(item);
      if (!mountedRef.current || previewRequestIdRef.current !== requestId || !open) {
        result.revoke?.();
        return;
      }
      previewRevokeRef.current = result.revoke ?? null;
      setPreviewSrc(result.imageSrc);
    } catch (error) {
      if (!mountedRef.current || previewRequestIdRef.current !== requestId || !open) {
        return;
      }
      const normalized = getVisibleErrorMessage(error, 'results');
      setPreviewError(normalized || t(previewErrorMessageKey));
    } finally {
      if (mountedRef.current && previewRequestIdRef.current === requestId && open) {
        setPreviewLoading(false);
      }
    }
  };

  const busy = isUploading || isDeleting || isReplacing;

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
              {copy.contextOverline}
            </Typography>
            <Typography component="h2" variant="h6" sx={{ fontWeight: 600, lineHeight: 1.2, mt: 0.25 }}>
              {copy.title}
            </Typography>
            {copy.subtitle ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                {copy.subtitle}
              </Typography>
            ) : null}
          </Box>
          <IconButton aria-label={copy.closeAria} onClick={onClose} size="small" edge="end">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, px: 2.5, py: 2 }}>
          {showUpload ? (
            <input
              ref={fileInputRef}
              type="file"
              accept={uploadAccept}
              multiple
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
          ) : null}
          {showReplace ? (
            <input
              ref={replaceInputRef}
              type="file"
              accept={uploadAccept}
              style={{ display: 'none' }}
              onChange={handleReplaceFileChange}
            />
          ) : null}
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
                <Typography variant="subtitle2">{copy.managementTitle}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {copy.managementBody}
                </Typography>
                {showUpload && onUpload ? (
                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                    <Button variant="contained" size="small" onClick={handleUploadClick} disabled={busy}>
                      {isUploading ? t('common.uploading') : copy.uploadButton}
                    </Button>
                  </Box>
                ) : null}
                {uploadError ? <ErrorAlert message={uploadError} /> : null}
                {replaceError ? <ErrorAlert message={replaceError} /> : null}
                {deleteError ? <ErrorAlert message={deleteError} /> : null}
              </Box>

              {items.length === 0 ? (
                <EmptyState title={copy.emptyTitle} message={copy.emptyMessage} />
              ) : (
                <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
                  {items.map((item, index) => (
                    <Box key={item.id}>
                      {index > 0 ? <Divider /> : null}
                      <ImageAssetCard
                        title={item.filename}
                        subtitle={getItemSubtitle(item)}
                        actions={
                          <>
                            <Button variant="outlined" size="small" onClick={() => void handlePreview(item)}>
                              {copy.preview}
                            </Button>
                            {showReplace && onReplace ? (
                              <Button
                                variant="outlined"
                                size="small"
                                onClick={() => handleReplaceClick(item)}
                                disabled={busy}
                              >
                                {isReplacing && replacingAssetId === item.id
                                  ? t('common.replacing')
                                  : (copy.replace ?? '')}
                              </Button>
                            ) : null}
                            <Button
                              variant="outlined"
                              color="error"
                              size="small"
                              onClick={() => setDeleteTarget(item)}
                              disabled={busy}
                            >
                              {copy.delete}
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
        open={open && Boolean(previewTarget)}
        onClose={clearPreview}
        title={previewTarget?.filename ?? copy.imagePreviewTitle}
        src={previewSrc}
        alt={previewTarget?.filename ?? copy.imagePreviewAlt}
        loading={previewLoading}
        error={previewError}
      />

      {open ? (
        <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} maxWidth="xs" fullWidth>
          <DialogTitle>{copy.deleteTitle}</DialogTitle>
          <DialogContent>
            <Typography variant="body2">
              {formatDeleteConfirm(deleteTarget?.filename ?? copy.deleteFallbackName)}
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDeleteTarget(null)} disabled={isDeleting}>
              {t('common.cancel')}
            </Button>
            <Button color="error" variant="contained" onClick={() => void handleDeleteConfirm()} disabled={isDeleting}>
              {isDeleting ? t('common.deleting') : copy.delete}
            </Button>
          </DialogActions>
        </Dialog>
      ) : null}
    </Drawer>
  );
}
