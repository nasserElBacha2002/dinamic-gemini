import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, List, ListItem, ListItemText, Typography } from '@mui/material';
import {
  labelForPositionAssignmentStatus,
  listJobPositionAssignments,
} from '../../api/positionReconciliationApi';
import { getPositionLabelUiCapabilities } from './positionLabelCapabilities';

export interface JobPositionSequenceDiagnosticsPanelProps {
  inventoryId: string;
  jobId: string | null | undefined;
}

export default function JobPositionSequenceDiagnosticsPanel({
  inventoryId,
  jobId,
}: JobPositionSequenceDiagnosticsPanelProps) {
  const enabled =
    getPositionLabelUiCapabilities().reconciliationEnabled && Boolean(inventoryId && jobId);
  const query = useQuery({
    queryKey: ['position-assignments', inventoryId, jobId],
    queryFn: () => listJobPositionAssignments(inventoryId, jobId!),
    enabled,
  });
  const items = useMemo(
    () =>
      [...(query.data?.items ?? [])].sort(
        (left, right) =>
          (left.sequence_number ?? Number.MAX_SAFE_INTEGER) -
          (right.sequence_number ?? Number.MAX_SAFE_INTEGER),
      ),
    [query.data?.items],
  );

  if (!enabled || query.isLoading || query.isError || items.length === 0) return null;

  return (
    <Box sx={{ mt: 2 }} data-testid="job-position-sequence-diagnostics-panel">
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        Diagnóstico de secuencia
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Recorrido de asignación de solo lectura.
      </Typography>
      <List dense sx={{ borderLeft: 2, borderColor: 'divider', ml: 1 }}>
        {items.map((item) => {
          const sequence =
            item.sequence_number == null ? 'Sin secuencia' : `Secuencia ${item.sequence_number}`;
          const position = item.position_name ? `Posición ${item.position_name}` : 'Sin asignar';
          const status = labelForPositionAssignmentStatus(item.assignment_status);
          return (
            <ListItem key={item.id}>
              <ListItemText
                primary={`${sequence} — ${position}`}
                secondary={`Producto ${item.result_id} → ${position} · ${status}`}
              />
            </ListItem>
          );
        })}
      </List>
    </Box>
  );
}
