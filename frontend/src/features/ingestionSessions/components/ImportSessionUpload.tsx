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
import type { UploadQueueItem } from '../hooks/useUploadCaptureItems';
import { useUploadCaptureItems } from '../hooks/useUploadCaptureItems';

interface ImportSessionUploadProps {
  inventoryId: string;
  aisleId: string;
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

function statusLabel(row: UploadQueueItem): string {
  if (row.state === 'uploaded') return 'Uploaded';
  if (row.state === 'failed') return 'Failed';
  if (row.state === 'uploading') return 'Uploading';
  return 'Pending';
}

export default function ImportSessionUpload({
  inventoryId,
  aisleId,
  sessionId,
  disabled = false,
  onCompleted,
}: ImportSessionUploadProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const uploadMutation = useUploadCaptureItems();

  const canSelect = !disabled && !uploadMutation.isPending;

  const startUpload = async (files: File[]) => {
    if (!files.length || !canSelect) return;
    try {
      await uploadMutation.mutateAsync({
        inventoryId,
        aisleId,
        sessionId,
        files,
        onQueueUpdate: setQueue,
      });
      onCompleted?.();
    } catch {
      // Queue already stores per-file failures; do not crash whole panel.
    }
  };

  return (
    <Box>
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
          startUpload(Array.from(e.dataTransfer.files));
        }}
      >
        <Typography variant="subtitle2" gutterBottom>
          Upload imported media
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Drag and drop files here or select multiple files from your device.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
          <Button
            variant="contained"
            onClick={() => fileInputRef.current?.click()}
            disabled={!canSelect}
            startIcon={<CloudUploadOutlinedIcon />}
          >
            Select files
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

      {uploadMutation.isError ? (
        <Alert severity="warning" sx={{ mt: 2 }}>
          Upload completed with errors. Review file-level statuses below.
        </Alert>
      ) : null}

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
                      {statusLabel(row)}
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
