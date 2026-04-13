import { useState } from 'react';
import { Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ApiError, type Inventory } from '../../../api/types';
import { exportInventoryResultsCsv } from '../../../api/client';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { PageHeader } from '../../../components/shell';
import { StatusBadge, useAppSnackbar } from '../../../components/ui';
import type { InventoryHeaderViewModel } from '../adapters';

export interface InventoryDetailHeaderProps {
  inventory: Inventory;
  inventoryId: string;
  headerVm: InventoryHeaderViewModel;
  onOpenReferenceImages: () => void;
  onOpenCreateAisle: () => void;
}

export default function InventoryDetailHeader({
  inventory,
  inventoryId,
  headerVm,
  onOpenReferenceImages,
  onOpenCreateAisle,
}: InventoryDetailHeaderProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [exportingCsv, setExportingCsv] = useState(false);

  return (
    <PageHeader
      breadcrumbs={[{ label: t('aisle.breadcrumb_inventories'), to: '/' }]}
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
          <Button variant="outlined" size="small" onClick={onOpenReferenceImages}>
            {t('aisle.visual_refs_title')}
          </Button>
          {inventory.processing_mode === 'test' ? (
            <Button
              variant="outlined"
              size="small"
              data-testid="inventory-header-compare-runs"
              onClick={() => navigate(`/inventories/${inventoryId}/analytics/compare`)}
            >
              {t('analytics.compare_runs_link')}
            </Button>
          ) : null}
          <Button
            variant="outlined"
            size="small"
            disabled={!inventoryId || exportingCsv}
            onClick={async () => {
              if (!inventoryId) return;
              setExportingCsv(true);
              try {
                await exportInventoryResultsCsv(inventoryId);
              } catch (e) {
                const err = e instanceof ApiError ? e : new ApiError(String(e));
                showSnackbar(resolveApiErrorMessage(err, 'errors.export_failed'), 'error');
              } finally {
                setExportingCsv(false);
              }
            }}
          >
            {exportingCsv ? t('common.exporting') : t('aisle.export_csv')}
          </Button>
          <Button variant="contained" size="small" onClick={onOpenCreateAisle}>
            {t('aisle.create')}
          </Button>
        </Box>
      }
    />
  );
}
