import { useTranslation } from 'react-i18next';
import { Box, Button, Link as MuiLink, Tooltip, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import type { AisleIssueRow } from '../../analytics/types';
import { pathToAislePositions, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';

export interface AnalyticsSummaryAttentionListProps {
  rows: readonly AisleIssueRow[];
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
  emptyText: string;
}

export function AnalyticsSummaryAttentionList({
  rows,
  inventoryProcessingModeById,
  onOpenAisleDrilldown,
  emptyText,
}: AnalyticsSummaryAttentionListProps) {
  const { t } = useTranslation();

  if (!rows.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-summary-attention-empty">
        {emptyText}
      </Typography>
    );
  }

  return (
    <Box
      component="ul"
      sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexDirection: 'column', gap: 1 }}
      data-testid="analytics-summary-attention-list"
    >
      {rows.map((row) => {
        const eligibility = getCompareEligibility(inventoryProcessingModeById.get(row.inventory_id));
        const compareHref = eligibility.allowed
          ? pathToInventoryAnalyticsCompareMany(row.inventory_id, { aisleId: row.aisle_id })
          : '';
        const compareTooltip = eligibility.allowed
          ? ''
          : t(compareEligibilityTooltipKey(eligibility.reason));

        return (
          <Box
            component="li"
            key={`${row.inventory_id}-${row.aisle_id}`}
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              py: 1,
              px: 1.25,
              border: 1,
              borderColor: 'divider',
              borderRadius: 1,
            }}
            data-testid={`analytics-overview-aisle-${row.aisle_id}`}
          >
            <Box sx={{ minWidth: 0, flex: '1 1 12rem' }}>
              <Typography variant="body2" fontWeight={600} noWrap>
                <MuiLink
                  component={RouterLink}
                  to={pathToAislePositions(row.inventory_id, row.aisle_id)}
                  underline="hover"
                >
                  {row.aisle_code}
                </MuiLink>
                <Typography component="span" variant="body2" color="text.secondary" fontWeight={400}>
                  {' · '}
                  {row.inventory_name}
                </Typography>
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" noWrap>
                {t('analyticsDashboard.visual.attentionReviewRequired', { count: row.needs_review_count })}
                {row.most_common_issue ? ` · ${row.most_common_issue}` : ''}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 0.5, flexShrink: 0 }}>
              <Button
                size="small"
                variant="text"
                onClick={() => onOpenAisleDrilldown(row.inventory_id, row.aisle_id)}
                data-testid={`overview-aisle-drilldown-${row.aisle_id}`}
              >
                {t('analyticsDashboard.drilldown.openAnalytics')}
              </Button>
              <Tooltip title={compareTooltip}>
                <span>
                  <Button
                    size="small"
                    variant="outlined"
                    component={eligibility.allowed ? RouterLink : 'button'}
                    to={eligibility.allowed ? compareHref : undefined}
                    disabled={!eligibility.allowed}
                    data-testid={`overview-aisle-compare-${row.aisle_id}`}
                  >
                    {t('analyticsDashboard.inventories.compareRuns')}
                  </Button>
                </span>
              </Tooltip>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
