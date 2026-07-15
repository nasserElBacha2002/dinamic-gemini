import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Typography,
  type DialogProps,
} from '@mui/material';
import type { BulkUploadProgressSnapshot } from '../../features/uploads';

export interface PhotoUploadProgressDialogProps {
  open: boolean;
  progress?: BulkUploadProgressSnapshot | null;
  onCancel?: () => void;
  onRetryFailed?: () => void;
}

function ignoreCloseWhileUploading(
  _event: object,
  reason: 'backdropClick' | 'escapeKeyDown'
): void {
  if (reason === 'backdropClick' || reason === 'escapeKeyDown') return;
}

/**
 * Dialog shown while photo uploads are in progress.
 * When ``progress`` is provided, shows global byte-based progress and actions.
 */
export default function PhotoUploadProgressDialog({
  open,
  progress,
  onCancel,
  onRetryFailed,
}: PhotoUploadProgressDialogProps) {
  const { t } = useTranslation();

  const handleClose: DialogProps['onClose'] = (_event, reason) => {
    ignoreCloseWhileUploading(_event, reason);
  };

  const done =
    progress?.phase === 'completed' ||
    progress?.phase === 'completed_with_errors' ||
    progress?.phase === 'cancelled';
  const showRetry =
    done && (progress?.failedCount ?? 0) > 0 && typeof onRetryFailed === 'function';

  return (
    <Dialog
      open={open}
      disableEscapeKeyDown={!done}
      onClose={handleClose}
      aria-labelledby="photo-upload-progress-title"
      data-testid="photo-upload-progress-dialog"
    >
      <DialogTitle id="photo-upload-progress-title">{t('uploads.photos.dialogTitle')}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start', minWidth: 280 }}>
          {!done ? <CircularProgress size={24} aria-hidden /> : null}
          <Box sx={{ flex: 1 }}>
            {progress ? (
              <>
                <Typography variant="body1">
                  {t('uploads.photos.progressCount', {
                    completed: progress.completedCount,
                    total: progress.totalCount,
                    defaultValue: `Subiendo {{completed}} de {{total}} fotos`,
                  })}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  {progress.progressPct} %{progress.failedCount > 0
                    ? ` · ${t('uploads.photos.failedCount', {
                        count: progress.failedCount,
                        defaultValue: '{{count}} archivos con errores',
                      })}`
                    : ''}
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={progress.progressPct}
                  sx={{ mt: 1.5 }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                  {t('uploads.photos.batchProgress', {
                    completed: progress.batchesCompleted,
                    total: progress.batchesTotal,
                    defaultValue: 'Lotes {{completed}} / {{total}}',
                  })}
                </Typography>
              </>
            ) : (
              <Typography variant="body1">{t('uploads.photos.progress')}</Typography>
            )}
            {!done ? (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                {t('uploads.photos.waitBeforeLeaving')}
              </Typography>
            ) : null}
          </Box>
        </Box>
      </DialogContent>
      {(onCancel && !done) || showRetry || done ? (
        <DialogActions>
          {onCancel && !done ? (
            <Button onClick={onCancel} color="inherit">
              {t('uploads.photos.cancel', { defaultValue: 'Cancelar' })}
            </Button>
          ) : null}
          {showRetry ? (
            <Button onClick={onRetryFailed} variant="contained">
              {t('uploads.photos.retryFailed', { defaultValue: 'Reintentar fallidos' })}
            </Button>
          ) : null}
        </DialogActions>
      ) : null}
    </Dialog>
  );
}
