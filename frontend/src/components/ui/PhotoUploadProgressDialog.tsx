import { useTranslation } from 'react-i18next';
import {
  Box,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  Typography,
  type DialogProps,
} from '@mui/material';

export interface PhotoUploadProgressDialogProps {
  open: boolean;
}

/** Ignore backdrop/Escape close while upload is in progress (blocking dialog). */
function ignoreCloseWhileUploading(
  _event: object,
  reason: 'backdropClick' | 'escapeKeyDown'
): void {
  if (reason === 'backdropClick' || reason === 'escapeKeyDown') return;
}

/**
 * Blocking dialog shown while photo uploads are in progress.
 * Callers must also disable close actions and duplicate submits while `open` is true.
 *
 * Render exactly one instance per active upload flow (page table, drawer, or import session).
 */
export default function PhotoUploadProgressDialog({ open }: PhotoUploadProgressDialogProps) {
  const { t } = useTranslation();

  const handleClose: DialogProps['onClose'] = (_event, reason) => {
    ignoreCloseWhileUploading(_event, reason);
  };

  return (
    <Dialog
      open={open}
      disableEscapeKeyDown
      onClose={handleClose}
      aria-labelledby="photo-upload-progress-title"
      data-testid="photo-upload-progress-dialog"
    >
      <DialogTitle id="photo-upload-progress-title">{t('uploads.photos.dialogTitle')}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
          <CircularProgress size={24} aria-hidden />
          <Box>
            <Typography variant="body1">{t('uploads.photos.progress')}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {t('uploads.photos.waitBeforeLeaving')}
            </Typography>
          </Box>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
