import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import ErrorOutlineOutlinedIcon from '@mui/icons-material/ErrorOutlineOutlined';
import CheckCircleOutlineOutlinedIcon from '@mui/icons-material/CheckCircleOutlineOutlined';
import HourglassTopOutlinedIcon from '@mui/icons-material/HourglassTopOutlined';
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
} from '@mui/material';
import { useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { ErrorAlert, PhotoUploadProgressDialog, useAppSnackbar } from '../../../components/ui';
import { useBeforeUnloadWarning } from '../../../hooks/useBeforeUnloadWarning';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { maxFilesPerUploadHelperText } from '../../../utils/uploadFileLimits';
import type { UploadQueueItem } from '../hooks/useUploadCaptureItems';
import { useUploadCaptureItems } from '../hooks/useUploadCaptureItems';

interface ImportSessionUploadProps {
  inventoryId: string;
  aisleId?: string;
  sessionId: string;
  disabled?: boolean;
  onCompleted?: () => void;
}

function statusIcon(row: UploadQueueItem) {
  if (row.state === 'uploaded') return <CheckCircleOutlineOutlinedIcon color="success" fontSize="small" />;
  if (row.state === 'failed') return <ErrorOutlineOutlinedIcon color="error" fontSize="small" />;
  if (row.state === 'uploading') return <HourglassTopOutlinedIcon color="info" fontSize="small" />;
  return <CloudUploadOutlinedIcon color="disabled" fontSize="small" />;
}

function statusLabel(row: UploadQueueItem, t: TFunction): string {
  if (row.state === 'uploaded') return t('ingestion_sessions.upload.status.uploaded');
  if (row.state === 'failed') return t('ingestion_sessions.upload.status.failed');
  if (row.state === 'uploading') return t('ingestion_sessions.upload.status.uploading');
  return t('ingestion_sessions.upload.status.pending');
}

export default function ImportSessionUpload({
  inventoryId,
  aisleId,
  sessionId,
  disabled = false,
  onCompleted,
}: ImportSessionUploadProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [lastSummary, setLastSummary] = useState<{ ok: number; fail: number } | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [progressSnap, setProgressSnap] = useState<
    import('../../uploads').BulkUploadProgressSnapshot | null
  >(null);
  const uploadMutation = useUploadCaptureItems();
  const isUploadingPhotos = uploadMutation.isPending;

  useBeforeUnloadWarning(isUploadingPhotos);

  const canSelect = !disabled && !isUploadingPhotos;

  const startUpload = async (files: File[]) => {
    if (!files.length || !canSelect) return;
    setSelectionError(null);
    setUploadError(null);
    setLastSummary(null);
    try {
      const result = await uploadMutation.mutateAsync({
        inventoryId,
        sessionId,
        aisleId,
        files,
        onQueueUpdate: setQueue,
        onProgress: setProgressSnap,
      });
      setLastSummary({ ok: result.uploadedCount, fail: result.failedCount });
      if (result.failedCount === 0) {
        showSnackbar(t('uploads.photos.success'), 'success');
      } else if (result.uploadedCount === 0) {
        const message = t('uploads.photos.error');
        setUploadError(message);
        showSnackbar(message, 'error');
      }
      onCompleted?.();
    } catch (err) {
      const message = resolveApiErrorMessage(err, 'uploads.photos.error');
      setUploadError(message);
      showSnackbar(message, 'error');
    }
  };

  const summaryNode =
    lastSummary != null ? (
      <Alert
        severity={lastSummary.fail === 0 ? 'success' : lastSummary.ok === 0 ? 'error' : 'warning'}
        sx={{ mt: 2 }}
      >
        {lastSummary.fail === 0
          ? t('ingestion_sessions.upload.summary_ok', { ok: lastSummary.ok })
          : lastSummary.ok === 0
            ? t('ingestion_sessions.upload.summary_all_failed', { fail: lastSummary.fail })
            : t('ingestion_sessions.upload.summary_mixed', { ok: lastSummary.ok, fail: lastSummary.fail })}
      </Alert>
    ) : null;

  return (
    <Box>
      <PhotoUploadProgressDialog open={isUploadingPhotos} progress={progressSnap} />

      <Paper
        variant="outlined"
        sx={{
          p: 2,
          borderStyle: 'dashed',
          borderColor: dragOver ? 'primary.main' : 'divider',
          bgcolor: dragOver ? 'action.hover' : 'background.paper',
        }}
        onDragOver={(e) => {
          if (!canSelect) return;
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          if (!canSelect) return;
          e.preventDefault();
          setDragOver(false);
          void startUpload(Array.from(e.dataTransfer.files));
        }}
      >
        <Typography variant="subtitle2" gutterBottom>
          {t('ingestion_sessions.upload.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {t('ingestion_sessions.upload.subtitle')}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {maxFilesPerUploadHelperText()}
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
          <Button
            variant="contained"
            onClick={() => fileInputRef.current?.click()}
            disabled={!canSelect}
            startIcon={<CloudUploadOutlinedIcon />}
          >
            {t('ingestion_sessions.upload.select_files')}
          </Button>
        </Box>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            void startUpload(files);
            e.currentTarget.value = '';
          }}
        />
      </Paper>

      {selectionError ? (
        <Alert severity="error" sx={{ mt: 2 }}>
          {selectionError}
        </Alert>
      ) : null}

      {uploadMutation.isError ? (
        <Alert severity="warning" sx={{ mt: 2 }}>
          {t('ingestion_sessions.upload.error_summary')}
        </Alert>
      ) : null}

      {uploadError ? (
        <Box sx={{ mt: 2 }} data-testid="import-session-upload-error">
          <ErrorAlert message={uploadError} onClose={() => setUploadError(null)} />
        </Box>
      ) : null}

      {summaryNode}

      {queue.length > 0 ? (
        <List dense sx={{ mt: 1 }}>
          {queue.map((row) => (
            <ListItem key={row.key} divider>
              <ListItemIcon>{statusIcon(row)}</ListItemIcon>
              <ListItemText
                primary={row.file.name}
                secondary={
                  <>
                    <Typography variant="caption" color="text.secondary">
                      {statusLabel(row, t)}
                    </Typography>
                    {row.state === 'uploading' ? <LinearProgress variant="determinate" value={row.progressPct} /> : null}
                    {row.error ? (
                      <Typography variant="caption" color="error.main" display="block">
                        {row.error}
                      </Typography>
                    ) : null}
                  </>
                }
              />
            </ListItem>
          ))}
        </List>
      ) : null}
    </Box>
  );
}
