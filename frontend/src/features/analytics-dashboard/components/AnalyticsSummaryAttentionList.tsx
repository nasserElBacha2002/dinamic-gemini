import { useTranslation } from 'react-i18next';
import { Box, Link as MuiLink, Tooltip, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import type { AisleIssueRow } from '../../analytics/types';
import { pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
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
      sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexDirection: 'column', gap: 0.75 }}
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
              display: 'grid',
              gridTemplateColumns: '1fr auto',
              alignItems: 'center',
              gap: 1,
              py: 0.75,
              borderBottom: 1,
              borderColor: 'divider',
              '&:last-child': { borderBottom: 0 },
            }}
            data-testid={`analytics-overview-aisle-${row.aisle_id}`}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" fontWeight={600} noWrap>
                {row.aisle_code}
                <Typography component="span" variant="body2" color="text.secondary" fontWeight={400}>
                  {' · '}
                  {row.inventory_name}
                </Typography>
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" noWrap>
                {row.most_common_issue
                  ? t('analyticsDashboard.visual.attentionPrimaryIssue', { issue: row.most_common_issue })
                  : t('analyticsDashboard.visual.attentionNoPrimaryIssue')}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {t('analyticsDashboard.visual.attentionReviewRequired', { count: row.needs_review_count })}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 1, flexShrink: 0, alignItems: 'center' }}>
              <MuiLink
                component="button"
                type="button"
                variant="body2"
                underline="hover"
                onClick={() => onOpenAisleDrilldown(row.inventory_id, row.aisle_id)}
                data-testid={`overview-aisle-drilldown-${row.aisle_id}`}
                sx={{ cursor: 'pointer', border: 0, bgcolor: 'transparent', p: 0 }}
              >
                {t('analyticsDashboard.summary.viewAction')}
              </MuiLink>
              {eligibility.allowed ? (
                <MuiLink
                  component={RouterLink}
                  to={compareHref}
                  variant="body2"
                  underline="hover"
                  data-testid={`overview-aisle-compare-${row.aisle_id}`}
                >
                  {t('analyticsDashboard.summary.compareAction')}
                </MuiLink>
              ) : compareTooltip ? (
                <Tooltip title={compareTooltip}>
                  <Typography variant="caption" color="text.disabled" component="span">
                    {t('analyticsDashboard.summary.compareAction')}
                  </Typography>
                </Tooltip>
              ) : null}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
