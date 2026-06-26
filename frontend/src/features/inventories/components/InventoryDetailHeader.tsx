import { Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ROUTE_HOME, pathToInventoryAnalyticsCompare } from '../../../constants/appRoutes';
import type { Inventory } from '../../../api/types';
import { PageHeader, type PageHeaderBreadcrumb } from '../../../components/shell';
import { StatusBadge } from '../../../components/ui';
import type { InventoryHeaderViewModel } from '../adapters';
import InventoryExportMenu from './InventoryExportMenu';

export interface InventoryDetailHeaderProps {
  inventory: Inventory;
  inventoryId: string;
  headerVm: InventoryHeaderViewModel;
  onOpenCreateAisle: () => void;
}

export default function InventoryDetailHeader({
  inventory,
  inventoryId,
  headerVm,
  onOpenCreateAisle,
}: InventoryDetailHeaderProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const breadcrumbs: PageHeaderBreadcrumb[] = [
    { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
  ];

  return (
    <PageHeader
      breadcrumbs={breadcrumbs}
      title={headerVm.title}
      subtitle={
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1 }}>
            <StatusBadge label={headerVm.statusLabel} semantic={headerVm.statusSemantic} />
            <StatusBadge label={headerVm.processingModeLabel} semantic={headerVm.processingModeSemantic} />
          </Box>
          {headerVm.primaryConfigCaption ? (
            <Typography variant="caption" color="text.secondary" display="block">
              {headerVm.primaryConfigCaption}
            </Typography>
          ) : null}
          <Box component="span" sx={{ color: 'text.secondary', typography: 'caption' }}>
            {headerVm.createdDateCaption}
          </Box>
        </Box>
      }
      actions={
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
          {inventory.processing_mode === 'test' ? (
            <Button
              variant="outlined"
              size="small"
              data-testid="inventory-header-compare-runs"
              onClick={() => navigate(pathToInventoryAnalyticsCompare(inventoryId))}
            >
              {t('analytics.compare_runs_link')}
            </Button>
          ) : null}
          <InventoryExportMenu inventoryId={inventoryId} />
          <Button variant="contained" size="small" onClick={onOpenCreateAisle}>
            {t('aisle.create')}
          </Button>
        </Box>
      }
    />
  );
}
