import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Paper } from '@mui/material';
import { CompareManyRunsWorkspace } from '../../analytics/compare/CompareManyRunsWorkspace';
import { getCompareEligibility } from '../types';

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

  if (!inventoryId) {
    return (
      <Box data-testid="analytics-compare-tab">
        <Alert severity="info">{t('analyticsDashboard.compare.selectInventoryHint')}</Alert>
      </Box>
    );
  }

  if (!eligibility.allowed) {
    return (
      <Box data-testid="analytics-compare-tab">
        <Alert severity="warning" data-testid="analytics-compare-unavailable">
          {eligibility.reason === 'unknown_mode'
            ? t('analyticsDashboard.compare.unknownModeTooltip')
            : t('analyticsDashboard.partial.compareNotAvailable')}
        </Alert>
      </Box>
    );
  }

  return (
    <Box data-testid="analytics-compare-tab">
      <Paper variant="outlined" sx={{ p: 2 }}>
      <CompareManyRunsWorkspace
        key={`${inventoryId}:${aisleId}`}
        mode="embedded"
        inventoryId={inventoryId}
        initialAisleId={aisleId || undefined}
        inventoryName={inventoryName}
        onNavigateToStandalone={(href) => navigate(href)}
      />
      </Paper>
    </Box>
  );
}
