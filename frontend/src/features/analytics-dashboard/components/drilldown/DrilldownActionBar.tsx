import { useTranslation } from 'react-i18next';
import { Box, Button, Tooltip } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { compareEligibilityTooltipKey } from '../../types';
import type { CompareEligibility } from '../../types';

export interface DrilldownActionBarProps {
  compareEligibility: CompareEligibility;
  compareHref: string;
  primaryActions: readonly {
    id: string;
    label: string;
    href?: string;
    onClick?: () => void;
    variant?: 'text' | 'outlined' | 'contained';
    testId?: string;
  }[];
}

export function DrilldownActionBar({ compareEligibility, compareHref, primaryActions }: DrilldownActionBarProps) {
  const { t } = useTranslation();
  const compareTooltip = compareEligibility.allowed
    ? ''
    : t(compareEligibilityTooltipKey(compareEligibility.reason));

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }} data-testid="analytics-drilldown-actions">
      {primaryActions.map((action) => {
        const btn = (
          <Button
            key={action.id}
            size="small"
            variant={action.variant ?? 'outlined'}
            component={action.href ? RouterLink : 'button'}
            to={action.href}
            onClick={action.onClick}
            data-testid={action.testId}
          >
            {action.label}
          </Button>
        );
        return action.href ? btn : <span key={action.id}>{btn}</span>;
      })}
      <Tooltip title={compareTooltip}>
        <span>
          <Button
            size="small"
            variant="contained"
            component={compareEligibility.allowed ? RouterLink : 'button'}
            to={compareEligibility.allowed ? compareHref : undefined}
            disabled={!compareEligibility.allowed}
            data-testid="analytics-drilldown-compare"
          >
            {t('analyticsDashboard.drilldown.compareRuns')}
          </Button>
        </span>
      </Tooltip>
    </Box>
  );
}
