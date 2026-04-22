import ImageOutlinedIcon from '@mui/icons-material/ImageOutlined';
import {
  Avatar,
  Box,
  Button,
  Divider,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import { useMemo } from 'react';
import { formatDate } from '../../../utils/formatDate';
import type { CaptureSessionDetailResponse, CaptureSessionItemResponse } from '../../../types/captureSession';
import ImportSessionUpload from './ImportSessionUpload';

interface ImportSessionDetailProps {
  detail: CaptureSessionDetailResponse;
  canUpload: boolean;
  canClose: boolean;
  closing: boolean;
  onCloseSession: () => void;
  onRefresh: () => void;
}

function sortItemsByEffectiveCaptureTime(items: CaptureSessionItemResponse[]): CaptureSessionItemResponse[] {
  return [...items].sort((a, b) => {
    const t1 = a.effective_capture_time ? new Date(a.effective_capture_time).getTime() : Number.MAX_SAFE_INTEGER;
    const t2 = b.effective_capture_time ? new Date(b.effective_capture_time).getTime() : Number.MAX_SAFE_INTEGER;
    return t1 - t2;
  });
}

export default function ImportSessionDetail({
  detail,
  canUpload,
  canClose,
  closing,
  onCloseSession,
  onRefresh,
}: ImportSessionDetailProps) {
  const sortedItems = useMemo(() => sortItemsByEffectiveCaptureTime(detail.items), [detail.items]);
  const noItems = sortedItems.length === 0;

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6">Import Session</Typography>
        <Typography variant="body2" color="text.secondary">
          ID: {detail.session.id}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Status: {detail.session.status}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Created: {formatDate(detail.session.created_at)}
        </Typography>
      </Box>

      <Divider />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <Button variant="contained" onClick={onCloseSession} disabled={!canClose || closing}>
          Close Session
        </Button>
      </Stack>

      <ImportSessionUpload
        inventoryId={detail.session.inventory_id}
        aisleId={detail.session.aisle_id}
        sessionId={detail.session.id}
        disabled={!canUpload}
        onCompleted={onRefresh}
      />

      {noItems ? (
        <Typography color="text.secondary">Upload images to begin.</Typography>
      ) : (
        <List dense>
          {sortedItems.map((item) => (
            <ListItem key={item.id} divider alignItems="flex-start">
              <ListItemAvatar>
                <Avatar variant="rounded">
                  <ImageOutlinedIcon />
                </Avatar>
              </ListItemAvatar>
              <ListItemText
                primary={item.original_filename || item.staging_storage_key}
                secondary={
                  <Box component="span" sx={{ display: 'block' }}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      import_status: {item.import_status}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      effective_capture_time:{' '}
                      {item.effective_capture_time ? formatDate(item.effective_capture_time) : 'N/A'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      time_source: {item.time_source ?? 'N/A'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      time_confidence:{' '}
                      {typeof item.time_confidence === 'number' ? item.time_confidence.toFixed(2) : 'N/A'}
                    </Typography>
                  </Box>
                }
              />
            </ListItem>
          ))}
        </List>
      )}
    </Stack>
  );
}
