import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { AnalyticsCostWarningsBlock } from '../AnalyticsCostWarningsBlock';
import type { AnalyticsCostWarningModel } from '../../adapters/analyticsCostWarnings';

export interface DrilldownScopeWarningsProps {
  warnings: readonly AnalyticsCostWarningModel[];
}

export function DrilldownScopeWarnings({ warnings }: DrilldownScopeWarningsProps) {
  const { t } = useTranslation();

  if (!warnings.length) return null;

  return (
    <Box sx={{ mb: 2 }} data-testid="analytics-drilldown-scope-warnings">
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        {t('analyticsDashboard.drilldown.scopeWarningsTitle')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        {t('analyticsDashboard.drilldown.scopeWarningsHelper')}
      </Typography>
      <AnalyticsCostWarningsBlock warnings={warnings} compact />
    </Box>
  );
}
