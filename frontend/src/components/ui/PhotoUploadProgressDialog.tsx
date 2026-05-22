import { useTranslation } from 'react-i18next';
import { Box, CircularProgress, Dialog, DialogContent, DialogTitle, Typography } from '@mui/material';

export interface PhotoUploadProgressDialogProps {
  open: boolean;
}

/**
 * Blocking dialog shown while photo uploads are in progress.
 * Callers must also disable close actions and duplicate submits while `open` is true.
 */
export default function PhotoUploadProgressDialog({ open }: PhotoUploadProgressDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      disableEscapeKeyDown
      onClose={() => {}}
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
