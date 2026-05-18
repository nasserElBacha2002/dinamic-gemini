import { useTranslation } from 'react-i18next';
import { Box, Drawer, Typography } from '@mui/material';
import type { AnalyticsCostSummaryResponse, Inventory } from '../../../../api/types';
import { DrawerHeader } from '../../../../components/ui';
import type { useAnalyticsDashboard } from '../../../analytics/hooks';
import type { AnalyticsDrilldownState } from '../../types';
import {
  findAisleIssueRow,
  findInventoryPerformanceRow,
  resolveInventoryDisplayName,
} from '../../adapters/analyticsDrilldownViewModel';
import { AisleDrilldownPanel } from './AisleDrilldownPanel';
import { InventoryDrilldownPanel } from './InventoryDrilldownPanel';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsDrilldownDrawerProps {
  state: AnalyticsDrilldownState;
  onClose: () => void;
  analytics: AnalyticsBundle;
  costSummary: AnalyticsCostSummaryResponse | null | undefined;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  inventoriesById: ReadonlyMap<string, Inventory>;
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
}

export function AnalyticsDrilldownDrawer({
  state,
  onClose,
  analytics,
  costSummary,
  isCostLoading,
  inventoryProcessingModeById,
  inventoriesById,
  onOpenAisleDrilldown,
}: AnalyticsDrilldownDrawerProps) {
  const { t } = useTranslation();
  const open = state != null;

  const title =
    state?.type === 'inventory'
      ? (() => {
          const perf = findInventoryPerformanceRow(analytics.inventoryPerformance?.items, state.inventoryId);
          const meta = inventoriesById.get(state.inventoryId);
          return t('analyticsDashboard.drilldown.inventoryTitle', {
            name: resolveInventoryDisplayName(perf, meta, state.inventoryId),
          });
        })()
      : state?.type === 'aisle'
        ? (() => {
            const aisle = findAisleIssueRow(
              analytics.aisleIssues?.items,
              state.inventoryId,
              state.aisleId
            );
            return t('analyticsDashboard.drilldown.aisleTitle', {
              aisle: aisle?.aisle_code ?? state.aisleId,
              inventory: aisle?.inventory_name ?? state.inventoryId,
            });
          })()
        : '';

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      data-testid="analytics-drilldown-drawer"
      PaperProps={{
        sx: { width: { xs: '100%', sm: 560, md: 680 }, maxWidth: '100%' },
      }}
    >
      <DrawerHeader
        title={
          <Typography variant="h6" component="h2" id="analytics-drilldown-title">
            {title}
          </Typography>
        }
        onClose={onClose}
        closeLabel={t('common.close')}
      />
      <Box
        role="region"
        aria-labelledby="analytics-drilldown-title"
        sx={{ p: 2.5, overflowY: 'auto', flex: 1 }}
      >
        {state?.type === 'inventory' ? (
          <InventoryDrilldownPanel
            inventoryId={state.inventoryId}
            analytics={analytics}
            costSummary={costSummary}
            isCostLoading={isCostLoading}
            inventoryMeta={inventoriesById.get(state.inventoryId)}
            inventoryProcessingModeById={inventoryProcessingModeById}
            onOpenAisleDrilldown={onOpenAisleDrilldown}
          />
        ) : null}
        {state?.type === 'aisle' ? (
          <AisleDrilldownPanel
            inventoryId={state.inventoryId}
            aisleId={state.aisleId}
            analytics={analytics}
            costSummary={costSummary}
            isCostLoading={isCostLoading}
            inventoryProcessingModeById={inventoryProcessingModeById}
            processingMode={inventoryProcessingModeById.get(state.inventoryId)}
          />
        ) : null}
      </Box>
    </Drawer>
  );
}
