import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Typography } from '@mui/material';
import { pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';

export interface AnalyticsCompareTabProps {
  inventoryId: string;
  aisleId: string;
  inventoryName: string | null;
  processingMode: string | undefined;
}

export function AnalyticsCompareTab({
  inventoryId,
  aisleId,
  inventoryName,
  processingMode,
}: AnalyticsCompareTabProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const eligibility = getCompareEligibility(processingMode);
  const href =
    eligibility.allowed && inventoryId
      ? pathToInventoryAnalyticsCompareMany(inventoryId, aisleId ? { aisleId } : undefined)
      : null;
  const disabledTooltip = eligibility.allowed ? '' : t(compareEligibilityTooltipKey(eligibility.reason));

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
        {inventoryId && !eligibility.allowed ? (
          <Alert severity="warning" data-testid="analytics-compare-unavailable">
            {eligibility.reason === 'unknown_mode'
              ? t('analyticsDashboard.compare.unknownModeTooltip')
              : t('analyticsDashboard.partial.compareNotAvailable')}
          </Alert>
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
          title={disabledTooltip || undefined}
          onClick={() => href && navigate(href)}
        >
          {t('analyticsDashboard.compare.openExistingFlow')}
        </Button>
      </AnalyticsSectionCard>
    </Box>
  );
}
