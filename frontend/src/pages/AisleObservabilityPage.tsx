import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Box, Button } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import AisleObservabilityWorkspace from '../components/AisleObservabilityWorkspace';
import { pathToInventory } from '../constants/appRoutes';
import { useAislesList } from '../hooks';

export default function AisleObservabilityPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const [searchParams] = useSearchParams();
  const jobId = searchParams.get('jobId');

  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId),
  });

  const aisleCode = useMemo(() => {
    const items = aislesQuery.data?.items ?? [];
    const match = items.find((a) => a.id === aisleId);
    return match?.code ?? aisleId ?? '';
  }, [aislesQuery.data?.items, aisleId]);

  const active = Boolean(inventoryId && aisleId);

  return (
    <Box sx={{ p: 2, maxWidth: 1600, mx: 'auto' }} data-testid="aisle-observability-page">
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate(pathToInventory(inventoryId ?? ''))}
        sx={{ mb: 1 }}
      >
        {t('jobs.obs_back_inventory')}
      </Button>
      {active ? (
        <AisleObservabilityWorkspace
          inventoryId={inventoryId!}
          aisleId={aisleId!}
          aisleCode={aisleCode}
          initialSelectedJobId={jobId}
          active={active}
          onAislesInvalidate={() => aislesQuery.refetch()}
        />
      ) : null}
    </Box>
  );
}
