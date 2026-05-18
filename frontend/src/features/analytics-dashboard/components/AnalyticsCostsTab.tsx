import { useTranslation } from 'react-i18next';
import { Box, Button, Typography } from '@mui/material';
import { MetricUnavailableCards, MetricUnavailableState } from './MetricUnavailableState';
import { AnalyticsSectionCard } from './AnalyticsSectionCard';
import { buildUnavailableGlobalCostKpis } from '../adapters/analyticsDashboardViewModel';
export interface AnalyticsCostsTabProps {
  onGoToCompare: () => void;
}

export function AnalyticsCostsTab({ onGoToCompare }: AnalyticsCostsTabProps) {
  const { t } = useTranslation();
  const unavailable = buildUnavailableGlobalCostKpis(t);

  return (
    <Box data-testid="analytics-costs-tab">
      <MetricUnavailableState
        title={t('analyticsDashboard.costs.globalUnavailableTitle')}
        description={t('analyticsDashboard.costs.globalUnavailableDescription')}
      />
      <AnalyticsSectionCard title={t('analyticsDashboard.costs.globalUnavailableTitle')}>
        <Box data-testid="global-cost-unavailable-cards">
          <MetricUnavailableCards
            cards={unavailable.map((c) => ({
              label: c.label,
              value: String(c.value),
              description: c.description,
            }))}
          />
        </Box>
      </AnalyticsSectionCard>
      <AnalyticsSectionCard title={t('analyticsDashboard.costs.perCompareSectionTitle')}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('analyticsDashboard.costs.compareAvailableDescription')}
        </Typography>
        <Button variant="outlined" onClick={onGoToCompare} data-testid="analytics-costs-go-compare">
          {t('analyticsDashboard.costs.goToCompare')}
        </Button>
      </AnalyticsSectionCard>
    </Box>
  );
}
