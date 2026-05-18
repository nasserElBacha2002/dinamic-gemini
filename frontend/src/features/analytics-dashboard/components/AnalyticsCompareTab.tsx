import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Typography } from '@mui/material';
import { pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { inventoryAllowsCompare } from '../types';

export interface AnalyticsCompareTabProps {
  inventoryId: string;
  aisleId: string;
  inventoryName: string | null;
  processingMode: string | undefined;
  onOpenCompareTab?: () => void;
}

export function AnalyticsCompareTab({
  inventoryId,
  aisleId,
  inventoryName,
  processingMode,
}: AnalyticsCompareTabProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const canCompare = Boolean(inventoryId) && inventoryAllowsCompare(processingMode);
  const href =
    canCompare && inventoryId
      ? pathToInventoryAnalyticsCompareMany(inventoryId, aisleId ? { aisleId } : undefined)
      : null;

  return (
    <Box data-testid="analytics-compare-tab">
      <AnalyticsSectionCard
        title={t('analyticsDashboard.compare.title')}
        grainLabel={t('analyticsDashboard.grain_compare')}
        subtitle={t('analyticsDashboard.compare.description')}
      >
        {!inventoryId ? (
          <Alert severity="info">{t('analyticsDashboard.compare.selectInventoryHint')}</Alert>
        ) : null}
        {inventoryId && !canCompare ? (
          <Alert severity="warning">{t('analyticsDashboard.partial.compareNotAvailable')}</Alert>
        ) : null}
        {inventoryName ? (
          <Typography variant="body2" sx={{ mb: 1 }}>
            {t('common.inventory')}: {inventoryName}
            {aisleId ? ` · ${t('common.aisle')}` : ''}
          </Typography>
        ) : null}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {t('analyticsDashboard.compare.quantityDeltaNeutral')}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('analyticsDashboard.compare.notRecommendation')}
        </Typography>
        <Button
          variant="contained"
          disabled={!href}
          data-testid="analytics-open-compare-flow"
          title={!canCompare ? t('analyticsDashboard.compare.testOnlyTooltip') : undefined}
          onClick={() => href && navigate(href)}
        >
          {t('analyticsDashboard.compare.openExistingFlow')}
        </Button>
      </AnalyticsSectionCard>
    </Box>
  );
}
