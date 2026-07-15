import { Button, FormControl, InputLabel, MenuItem, Select, Stack } from '@mui/material';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '../../../components/shell';
import { ErrorAlert, SectionCard } from '../../../components/ui';
import { pathToIngestionSessionDetail } from '../../../constants/appRoutes';
import ImportSessionList from '../components/ImportSessionList';
import {
  useAisleOptions,
  useCaptureSessionsList,
  useCreateCaptureSession,
  useInventoryOptions,
} from '../hooks/useCaptureSessions';
import { buildSessionsListParams } from '../utils/ingestionSessionsListParams';
import { filterActiveAisles } from '../../../utils/aisleActive';

export default function IngestionSessionsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const inventoriesQuery = useInventoryOptions();
  const inventoryOptions = inventoriesQuery.data?.items ?? [];
  const [selectedInventoryId, setSelectedInventoryId] = useState<string>('');
  const [selectedAisleId, setSelectedAisleId] = useState<string>('');

  const activeInventoryId = selectedInventoryId || inventoryOptions[0]?.id || '';
  const aislesQuery = useAisleOptions(activeInventoryId, { enabled: Boolean(activeInventoryId) });
  const aisleOptions = filterActiveAisles(aislesQuery.data?.items ?? []);

  const sessionsQuery = useCaptureSessionsList(
    buildSessionsListParams(activeInventoryId, selectedAisleId),
    { enabled: Boolean(activeInventoryId) }
  );
  const createMutation = useCreateCaptureSession();

  const loadError = inventoriesQuery.error || aislesQuery.error || sessionsQuery.error;
  const createError = createMutation.error;

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('ingestion_sessions.page.title')}
        subtitle={t('ingestion_sessions.page.subtitle')}
        actions={
          <Button
            variant="contained"
            disabled={!activeInventoryId || createMutation.isPending}
            onClick={async () => {
              if (!activeInventoryId) return;
              const created = await createMutation.mutateAsync({
                inventoryId: activeInventoryId,
                aisleId: selectedAisleId.trim() || undefined,
              });
              navigate(pathToIngestionSessionDetail(created.id, created.inventory_id));
            }}
          >
            {t('ingestion_sessions.actions.new_import_session')}
          </Button>
        }
      />

      {loadError ? (
        <ErrorAlert error={loadError} context="ingestionSession" onRetry={() => sessionsQuery.refetch()} />
      ) : null}
      {createError ? (
        <ErrorAlert error={createError} context="ingestionSession" onClose={() => createMutation.reset()} />
      ) : null}

      <SectionCard title={t('ingestion_sessions.filters.title')}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <FormControl fullWidth>
            <InputLabel id="ingestion-inventory-label">{t('ingestion_sessions.filters.inventory')}</InputLabel>
            <Select
              labelId="ingestion-inventory-label"
              label={t('ingestion_sessions.filters.inventory')}
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
            <InputLabel id="ingestion-aisle-label">{t('ingestion_sessions.filters.aisle')}</InputLabel>
            <Select
              labelId="ingestion-aisle-label"
              label={t('ingestion_sessions.filters.aisle')}
              value={selectedAisleId}
              onChange={(e) => setSelectedAisleId(String(e.target.value))}
            >
              <MenuItem value="">
                {t('ingestion_sessions.filters.all_aisles')}
              </MenuItem>
              {aisleOptions.map((aisle) => (
                <MenuItem key={aisle.id} value={aisle.id}>
                  {aisle.code || aisle.id}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </SectionCard>

      <ImportSessionList
        title={t('ingestion_sessions.list.title')}
        sessions={sessionsQuery.data?.items ?? []}
        loading={sessionsQuery.isLoading}
        onOpen={(session) =>
          navigate(pathToIngestionSessionDetail(session.id, session.inventory_id))
        }
      />
    </Stack>
  );
}
