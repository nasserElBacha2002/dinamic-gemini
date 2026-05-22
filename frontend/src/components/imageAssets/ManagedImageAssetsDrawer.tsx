import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Divider, Drawer, Typography } from '@mui/material';
import { useBeforeUnloadWarning } from '../../hooks/useBeforeUnloadWarning';
import { getVisibleErrorMessage } from '../../utils/apiErrors';
import {
  isTooManyFilesForUpload,
  maxFilesPerUploadHelperText,
  tooManyFilesMessage,
} from '../../utils/uploadFileLimits';
import {
  ConfirmDialog,
  DrawerHeader,
  EmptyState,
  ErrorAlert,
  LoadingBlock,
  ImageAssetCard,
  ImagePreviewDialog,
  PhotoUploadProgressDialog,
  useAppSnackbar,
} from '../ui';
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
  /** When true, render as an in-page panel instead of a right Drawer. */
  embedded?: boolean;
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
  /** When false, file input does not allow multi-select (default true). */
  uploadMultiple?: boolean;
  /** Rendered inside the management panel before the upload button (e.g. optional metadata fields). */
  uploadExtras?: ReactNode;
  showReplace?: boolean;
  onReplace?: (assetId: string, file: File) => Promise<unknown>;
  isReplacing?: boolean;
  replaceError?: string | null;
  onDelete?: (assetId: string) => Promise<unknown>;
  isDeleting?: boolean;
  deleteError?: string | null;
  previewErrorMessageKey?: string;
  /** When this returns a non-empty string, preview is skipped and the message is shown (e.g. video in image-only viewer). */
  previewBlockedMessage?: (item: ManagedImageAssetItem) => string | null;
  formatDeleteConfirm?: (fileName: string) => string;
  /** When true: no upload/replace/delete UI, no management panel, preview only. */
  readOnly?: boolean;
  /** Passed to {@link LoadingBlock} while `isLoading` is true. */
  loadingMessage?: string;
}

export default function ManagedImageAssetsDrawer({
  open,
  embedded = false,
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
  uploadMultiple = true,
  uploadExtras,
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
  readOnly = false,
  loadingMessage,
}: ManagedImageAssetsDrawerProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const effectiveOpen = embedded || open;
  useBeforeUnloadWarning(isUploading);
  void previewErrorMessageKey;
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
  const [localUploadError, setLocalUploadError] = useState<string | null>(null);

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
    if (!effectiveOpen) {
      previewRequestIdRef.current += 1;
      if (previewRevokeRef.current) {
        previewRevokeRef.current();
        previewRevokeRef.current = null;
      }
    }
  }, [effectiveOpen]);

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
    if (files.length === 0 || !onUpload || isUploading) return;
    if (isTooManyFilesForUpload(files.length)) {
      setLocalUploadError(tooManyFilesMessage('aisle'));
      return;
    }
    setLocalUploadError(null);
    try {
      await onUpload(files);
      showSnackbar(t('uploads.photos.success'), 'success');
    } catch {
      showSnackbar(t('uploads.photos.error'), 'error');
    }
  };

  const guardedOnClose = useCallback(() => {
    if (isUploading) return;
    onClose();
  }, [isUploading, onClose]);

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
    if (!deleteTarget || !onDelete) return;
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
      if (!mountedRef.current || previewRequestIdRef.current !== requestId || !effectiveOpen) {
        result.revoke?.();
        return;
      }
      previewRevokeRef.current = result.revoke ?? null;
      setPreviewSrc(result.imageSrc);
    } catch (error) {
      if (!mountedRef.current || previewRequestIdRef.current !== requestId || !effectiveOpen) {
        return;
      }
      setPreviewError(getVisibleErrorMessage(error, 'results'));
    } finally {
      if (mountedRef.current && previewRequestIdRef.current === requestId && effectiveOpen) {
        setPreviewLoading(false);
      }
    }
  };

  const busy = isUploading || isDeleting || isReplacing;
  const effectiveUploadError = localUploadError ?? uploadError ?? null;
  const effectiveShowUpload = !readOnly && showUpload;
  const effectiveShowReplace = !readOnly && showReplace;

  const headerSection = embedded ? (
    <Box
      sx={{
        py: 1.5,
        px: 2.5,
        zIndex: 1,
        flexShrink: 0,
        borderBottom: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
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
  ) : (
    <DrawerHeader
      sx={{ py: 1.5, zIndex: 1 }}
      closeLabel={copy.closeAria}
      onClose={guardedOnClose}
      closeDisabled={isUploading}
      overline={
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5 }}>
          {copy.contextOverline}
        </Typography>
      }
      title={
        <Typography component="h2" variant="h6" sx={{ fontWeight: 600, lineHeight: 1.2, mt: 0.25 }}>
          {copy.title}
        </Typography>
      }
      subtitle={
        copy.subtitle ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
            {copy.subtitle}
          </Typography>
        ) : null
      }
    />
  );

  const scrollSection = (
    <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, px: 2.5, py: 2 }}>
          {effectiveShowUpload ? (
            <input
              ref={fileInputRef}
              type="file"
              accept={uploadAccept}
              multiple={uploadMultiple}
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
          ) : null}
          {effectiveShowReplace ? (
            <input
              ref={replaceInputRef}
              type="file"
              accept={uploadAccept}
              style={{ display: 'none' }}
              onChange={handleReplaceFileChange}
            />
          ) : null}
          {isLoading ? <LoadingBlock message={loadingMessage} /> : null}

          {!isLoading && errorMessage ? <ErrorAlert message={errorMessage} onRetry={onRetry} /> : null}

          {!isLoading && !errorMessage ? (
            <Box sx={{ display: 'grid', gap: 2 }}>
              {!readOnly ? (
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
                  <Typography variant="caption" color="text.secondary" display="block">
                    {maxFilesPerUploadHelperText()}
                  </Typography>
                  {uploadExtras ?? null}
                  {effectiveShowUpload && onUpload ? (
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      <Button variant="contained" size="small" onClick={handleUploadClick} disabled={busy}>
                        {isUploading ? t('uploads.photos.uploadingButton') : copy.uploadButton}
                      </Button>
                      {isUploading ? (
                        <Typography variant="caption" color="text.secondary" sx={{ width: '100%' }}>
                          {t('uploads.photos.waitBeforeLeaving')}
                        </Typography>
                      ) : null}
                    </Box>
                  ) : null}
                  {effectiveUploadError ? <ErrorAlert message={effectiveUploadError} /> : null}
                  {replaceError ? <ErrorAlert message={replaceError} /> : null}
                  {deleteError ? <ErrorAlert message={deleteError} /> : null}
                </Box>
              ) : null}

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
                            {effectiveShowReplace && onReplace ? (
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
                            {!readOnly && onDelete ? (
                              <Button
                                variant="outlined"
                                color="error"
                                size="small"
                                onClick={() => setDeleteTarget(item)}
                                disabled={busy}
                              >
                                {copy.delete}
                              </Button>
                            ) : null}
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
  );

  const shell = (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: embedded ? 'auto' : '100%',
        minHeight: embedded ? 320 : 0,
        maxHeight: embedded ? 'min(70vh, 720px)' : undefined,
        bgcolor: 'background.paper',
        ...(embedded
          ? { border: 1, borderColor: 'divider', borderRadius: 1, overflow: 'hidden' }
          : {}),
      }}
    >
      {headerSection}
      {scrollSection}
    </Box>
  );

  return (
    <>
      <PhotoUploadProgressDialog open={isUploading} />

      {embedded ? (
        shell
      ) : (
        <Drawer
          anchor="right"
          open={open}
          onClose={(_event, reason) => {
            if (isUploading && (reason === 'backdropClick' || reason === 'escapeKeyDown')) return;
            guardedOnClose();
          }}
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
          {shell}
        </Drawer>
      )}

      <ImagePreviewDialog
        open={effectiveOpen && Boolean(previewTarget)}
        onClose={clearPreview}
        title={previewTarget?.filename ?? copy.imagePreviewTitle}
        src={previewSrc}
        alt={previewTarget?.filename ?? copy.imagePreviewAlt}
        loading={previewLoading}
        error={previewError}
      />

      {effectiveOpen && !readOnly && onDelete && formatDeleteConfirm ? (
        <ConfirmDialog
          open={Boolean(deleteTarget)}
          onClose={() => setDeleteTarget(null)}
          title={copy.deleteTitle}
          description={
            <Typography variant="body2">
              {formatDeleteConfirm(deleteTarget?.filename ?? copy.deleteFallbackName)}
            </Typography>
          }
          cancelLabel={t('common.cancel')}
          confirmLabel={copy.delete}
          confirmPendingLabel={t('common.deleting')}
          onConfirm={() => void handleDeleteConfirm()}
          loading={isDeleting}
          confirmColor="error"
          maxWidth="xs"
        />
      ) : null}
    </>
  );
}
