import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import {
  labelForPositionAssignmentStatus,
  listJobPositionAssignments,
  type ProductPositionAssignmentDto,
} from '../../api/positionReconciliationApi';
import { ApiError } from '../../api/types';
import { getPositionLabelUiCapabilities } from './positionLabelCapabilities';

type AssignmentFilter = 'all' | 'assigned' | 'unassigned' | 'ambiguous';

export interface JobPositionAssignmentsPanelProps {
  inventoryId: string;
  jobId: string | null | undefined;
}

function matchesFilter(item: ProductPositionAssignmentDto, filter: AssignmentFilter): boolean {
  if (filter === 'assigned') return item.assignment_status === 'ASSIGNED_AUTOMATIC';
  if (filter === 'ambiguous') {
    return item.assignment_status === 'UNASSIGNED_AFTER_AMBIGUOUS_POSITION';
  }
  if (filter === 'unassigned') return item.assignment_status !== 'ASSIGNED_AUTOMATIC';
  return true;
}

export default function JobPositionAssignmentsPanel({
  inventoryId,
  jobId,
}: JobPositionAssignmentsPanelProps) {
  const reconciliationEnabled = getPositionLabelUiCapabilities().reconciliationEnabled;
  const [filter, setFilter] = useState<AssignmentFilter>('all');
  const query = useQuery({
    queryKey: ['position-assignments', inventoryId, jobId],
    queryFn: () => listJobPositionAssignments(inventoryId, jobId!),
    enabled: reconciliationEnabled && Boolean(inventoryId && jobId),
  });
  const items = useMemo(
    () => (query.data?.items ?? []).filter((item) => matchesFilter(item, filter)),
    [filter, query.data?.items],
  );

  if (!jobId) return null;

  if (!reconciliationEnabled) {
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        Reconciliación deshabilitada
      </Alert>
    );
  }

  if (query.isError) {
    const disabled = query.error instanceof ApiError && query.error.status === 404;
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        {disabled
          ? 'Reconciliación deshabilitada'
          : 'No se pudieron cargar las asignaciones de posición.'}
      </Alert>
    );
  }

  return (
    <Box sx={{ mt: 2 }} data-testid="job-position-assignments-panel">
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        Asignaciones de posición
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Resultado de reconciliación automático y de solo lectura.
      </Typography>

      <ToggleButtonGroup
        exclusive
        size="small"
        value={filter}
        onChange={(_, value: AssignmentFilter | null) => {
          if (value) setFilter(value);
        }}
        aria-label="Filtro de asignaciones"
        sx={{ mb: 1.5, flexWrap: 'wrap' }}
      >
        <ToggleButton value="all">Todas</ToggleButton>
        <ToggleButton value="assigned">Con posición</ToggleButton>
        <ToggleButton value="unassigned">Sin posición</ToggleButton>
        <ToggleButton value="ambiguous">Ambiguas</ToggleButton>
      </ToggleButtonGroup>

      {query.isLoading ? <CircularProgress size={22} aria-label="Cargando asignaciones" /> : null}
      {!query.isLoading && (query.data?.items.length ?? 0) === 0 ? (
        <Alert severity="info">No hay asignaciones de posición para este job.</Alert>
      ) : null}
      {!query.isLoading && (query.data?.items.length ?? 0) > 0 && items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No hay asignaciones para este filtro.
        </Typography>
      ) : null}
      {items.length > 0 ? (
        <TableContainer>
          <Table size="small" aria-label="Asignaciones de posición">
            <TableHead>
              <TableRow>
                <TableCell>Producto</TableCell>
                <TableCell>Secuencia</TableCell>
                <TableCell>Posición asignada</TableCell>
                <TableCell>Estado</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.result_id}</TableCell>
                  <TableCell>{item.sequence_number ?? 'Sin secuencia'}</TableCell>
                  <TableCell>{item.position_name ?? 'Sin asignar'}</TableCell>
                  <TableCell>{labelForPositionAssignmentStatus(item.assignment_status)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : null}
    </Box>
  );
}
