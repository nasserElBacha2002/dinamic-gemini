/**
 * Minimal Phase 3 panel: show position-label detections for the selected job.
 */

import { useQuery } from '@tanstack/react-query';
import { Alert, Box, List, ListItem, ListItemText, Typography } from '@mui/material';
import {
  labelForPositionDetectionStatus,
  listJobPositionDetections,
} from '../../api/positionLabelDetectionsApi';
import { getPositionLabelUiCapabilities } from './positionLabelCapabilities';

export interface JobPositionDetectionsPanelProps {
  inventoryId: string;
  jobId: string | null | undefined;
}

export default function JobPositionDetectionsPanel({
  inventoryId,
  jobId,
}: JobPositionDetectionsPanelProps) {
  const enabled = getPositionLabelUiCapabilities().labelsEnabled && Boolean(inventoryId && jobId);
  const query = useQuery({
    queryKey: ['position-detections', inventoryId, jobId],
    queryFn: () => listJobPositionDetections(inventoryId, jobId!),
    enabled,
  });

  if (!enabled || !jobId) {
    return null;
  }

  if (query.isLoading) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Cargando detecciones de posición…
      </Typography>
    );
  }

  if (query.isError) {
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        No se pudieron cargar las detecciones de posición (puede estar deshabilitado).
      </Alert>
    );
  }

  const items = (query.data?.items ?? []).filter((i) => i.status !== 'NO_LABEL');
  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Sin detecciones de etiqueta de posicionamiento en este job.
      </Typography>
    );
  }

  return (
    <Box sx={{ mt: 2 }} data-testid="job-position-detections-panel">
      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
        Detecciones de posicionamiento
      </Typography>
      <List dense>
        {items.map((item) => {
          const seq = item.sequence_number != null ? `Imagen ${item.sequence_number}` : item.asset_id;
          const posName = item.position_label?.name;
          const primary =
            item.status === 'VALID' && posName
              ? `${seq}: Posición ${posName}`
              : `${seq}: ${labelForPositionDetectionStatus(item.status)}`;
          const secondary = `Estado: ${item.status} · Firma: ${item.signature_status}`;
          return (
            <ListItem key={item.id} disableGutters>
              <ListItemText primary={primary} secondary={secondary} />
            </ListItem>
          );
        })}
      </List>
    </Box>
  );
}
