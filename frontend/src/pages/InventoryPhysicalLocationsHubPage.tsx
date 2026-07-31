/**
 * Inventory hub redirect: positioning labels are client-scoped.
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { Button, Typography } from '@mui/material';
import { PageHeader } from '../components/shell';
import { EmptyState, ErrorAlert, LoadingBlock, SectionCard } from '../components/ui';
import { pathToClientPhysicalLocations, pathToInventory, ROUTE_HOME } from '../constants/appRoutes';
import { useInventoryDetail } from '../hooks';

export default function InventoryPhysicalLocationsHubPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const safeInv = (inventoryId ?? '').trim();
  const inventoryQuery = useInventoryDetail(safeInv || undefined, { enabled: Boolean(safeInv) });
  const clientId = (inventoryQuery.data?.client_id ?? '').trim();

  useEffect(() => {
    if (clientId) {
      navigate(pathToClientPhysicalLocations(clientId), { replace: true });
    }
  }, [clientId, navigate]);

  if (!safeInv) {
    return <ErrorAlert message={t('aisle_locations.missing_route_params')} />;
  }

  if (inventoryQuery.isLoading) {
    return <LoadingBlock />;
  }

  if (!clientId) {
    return (
      <>
        <PageHeader
          breadcrumbs={[
            { label: t('inventories.breadcrumb'), to: ROUTE_HOME },
            { label: inventoryQuery.data?.name ?? safeInv, to: pathToInventory(safeInv) },
            { label: t('position_labels.title') },
          ]}
          title={t('position_labels.title')}
        />
        <SectionCard title={t('position_labels.title')}>
          <EmptyState
            title={t('position_labels.title')}
            message={t('position_labels.subtitle')}
            action={
              <Button component={RouterLink} to={pathToInventory(safeInv)} variant="outlined">
                {t('aisle_locations.hub_go_inventory')}
              </Button>
            }
          />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            {t('position_labels.subtitle')}
          </Typography>
        </SectionCard>
      </>
    );
  }

  return <LoadingBlock message={t('common.loading')} />;
}
