import { Button, FormControl, InputLabel, MenuItem, Select, Stack } from '@mui/material';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../../../components/shell';
import { ErrorAlert, SectionCard } from '../../../components/ui';
import { pathToIngestionSessionDetail } from '../../../constants/appRoutes';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { ApiError } from '../../../api/types';
import ImportSessionList from '../components/ImportSessionList';
import {
  useAisleOptions,
  useCaptureSessionsList,
  useCreateCaptureSession,
  useInventoryOptions,
} from '../hooks/useCaptureSessions';
import type { DataTableSortDirection } from '../../../components/ui';

export default function IngestionSessionsPage() {
  const navigate = useNavigate();
  const inventoriesQuery = useInventoryOptions();
  const inventoryOptions = inventoriesQuery.data?.items ?? [];
  const [selectedInventoryId, setSelectedInventoryId] = useState<string>('');
  const [selectedAisleId, setSelectedAisleId] = useState<string>('');
  const [sortDir, setSortDir] = useState<DataTableSortDirection>('desc');

  const activeInventoryId = selectedInventoryId || inventoryOptions[0]?.id || '';
  const aislesQuery = useAisleOptions(activeInventoryId, { enabled: Boolean(activeInventoryId) });
  const aisleOptions = aislesQuery.data?.items ?? [];
  const activeAisleId = selectedAisleId || aisleOptions[0]?.id || '';

  const sessionsQuery = useCaptureSessionsList(
    {
      inventoryId: activeInventoryId,
      aisleId: activeAisleId || undefined,
      page: 1,
      pageSize: 100,
    },
    { enabled: Boolean(activeInventoryId) }
  );
  const createMutation = useCreateCaptureSession();

  const loadErrorMessage = useMemo(() => {
    const err = inventoriesQuery.error || aislesQuery.error || sessionsQuery.error;
    if (!err) return null;
    return resolveApiErrorMessage(err, 'errors.request_failed');
  }, [aislesQuery.error, inventoriesQuery.error, sessionsQuery.error]);

  const createErrorMessage = useMemo(() => {
    if (!createMutation.error) return null;
    if (createMutation.error instanceof ApiError) return resolveApiErrorMessage(createMutation.error, 'errors.request_failed');
    return resolveApiErrorMessage(createMutation.error, 'errors.request_failed');
  }, [createMutation.error]);

  return (
    <Stack spacing={2}>
      <PageHeader
        title="Import Sessions"
        subtitle="Create, upload, and prepare sessions before preview."
        actions={
          <Button
            variant="contained"
            disabled={!activeInventoryId || !activeAisleId || createMutation.isPending}
            onClick={async () => {
              if (!activeInventoryId || !activeAisleId) return;
              const created = await createMutation.mutateAsync({
                inventoryId: activeInventoryId,
                aisleId: activeAisleId,
              });
              navigate(pathToIngestionSessionDetail(created.id, created.inventory_id, created.aisle_id));
            }}
          >
            New Import Session
          </Button>
        }
      />

      {loadErrorMessage ? <ErrorAlert message={loadErrorMessage} onRetry={() => sessionsQuery.refetch()} /> : null}
      {createErrorMessage ? <ErrorAlert message={createErrorMessage} onClose={() => createMutation.reset()} /> : null}

      <SectionCard title="Session filters">
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <FormControl fullWidth>
            <InputLabel id="ingestion-inventory-label">Inventory</InputLabel>
            <Select
              labelId="ingestion-inventory-label"
              label="Inventory"
              value={activeInventoryId}
              onChange={(e) => {
                const next = String(e.target.value);
                setSelectedInventoryId(next);
                setSelectedAisleId('');
              }}
            >
              {inventoryOptions.map((inv) => (
                <MenuItem key={inv.id} value={inv.id}>
                  {inv.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth disabled={!activeInventoryId}>
            <InputLabel id="ingestion-aisle-label">Aisle</InputLabel>
            <Select
              labelId="ingestion-aisle-label"
              label="Aisle"
              value={activeAisleId}
              onChange={(e) => setSelectedAisleId(String(e.target.value))}
            >
              {aisleOptions.map((aisle) => (
                <MenuItem key={aisle.id} value={aisle.id}>
                  {aisle.code || aisle.id}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </SectionCard>

      <SectionCard title="Import Sessions">
        <ImportSessionList
          sessions={sessionsQuery.data?.items ?? []}
          loading={sessionsQuery.isLoading}
          sortDir={sortDir}
          setSortDir={setSortDir}
          onOpen={(session) =>
            navigate(pathToIngestionSessionDetail(session.id, session.inventory_id, session.aisle_id))
          }
        />
      </SectionCard>
    </Stack>
  );
}
