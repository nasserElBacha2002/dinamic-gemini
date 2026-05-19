import { useTranslation } from 'react-i18next';
import { Box, Link as MuiLink, Tooltip, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import type { AisleIssueRow } from '../../analytics/types';
import { pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import type { BarChartDatum } from '../adapters/analyticsChartDatasets';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';

export interface QualityAislesAttentionRankingProps {
  rows: readonly AisleIssueRow[];
  barData: readonly BarChartDatum[];
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
  emptyText: string;
}

export function QualityAislesAttentionRanking({
  rows,
  barData,
  inventoryProcessingModeById,
  onOpenAisleDrilldown,
  emptyText,
}: QualityAislesAttentionRankingProps) {
  const { t } = useTranslation();

  if (!rows.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="analytics-quality-aisle-ranking-empty">
        {emptyText}
      </Typography>
    );
  }

  const max = Math.max(...barData.map((d) => d.value), 1);
  const rowById = new Map(rows.map((row) => [`${row.inventory_id}-${row.aisle_id}`, row]));

  return (
    <Box
      component="ul"
      data-testid="analytics-quality-aisle-ranking"
      sx={{ listStyle: 'none', m: 0, p: 0, display: 'flex', flexDirection: 'column', gap: 1.5 }}
    >
      {barData.map((bar) => {
        const row = rowById.get(bar.id);
        if (!row) return null;
        const widthPct = Math.max(4, (bar.value / max) * 100);
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
            key={bar.id}
            data-testid={`analytics-quality-aisle-${row.aisle_id}`}
            sx={{ minWidth: 0 }}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1, mb: 0.5 }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600} noWrap title={bar.label}>
                  {bar.label}
                </Typography>
                {row.most_common_issue ? (
                  <Typography variant="caption" color="text.secondary" display="block" noWrap>
                    {t('analyticsDashboard.visual.attentionPrimaryIssue', { issue: row.most_common_issue })}
                  </Typography>
                ) : null}
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexShrink: 0, alignItems: 'center' }}>
                <MuiLink
                  component="button"
                  type="button"
                  variant="body2"
                  underline="hover"
                  onClick={() => onOpenAisleDrilldown(row.inventory_id, row.aisle_id)}
                  data-testid={`quality-aisle-drilldown-${row.aisle_id}`}
                  sx={{ cursor: 'pointer', border: 0, bgcolor: 'transparent', p: 0 }}
                >
                  {t('analyticsDashboard.quality.viewInAnalytics')}
                </MuiLink>
                {eligibility.allowed ? (
                  <MuiLink
                    component={RouterLink}
                    to={compareHref}
                    variant="body2"
                    underline="hover"
                    data-testid={`quality-aisle-compare-${row.aisle_id}`}
                  >
                    {t('analyticsDashboard.quality.compareRuns')}
                  </MuiLink>
                ) : compareTooltip ? (
                  <Tooltip title={compareTooltip}>
                    <Typography variant="caption" color="text.disabled" component="span">
                      {t('analyticsDashboard.quality.compareRuns')}
                    </Typography>
                  </Tooltip>
                ) : null}
              </Box>
            </Box>
            <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden', mb: 0.35 }}>
              <Box sx={{ height: '100%', width: `${widthPct}%`, bgcolor: 'warning.main', borderRadius: 999 }} />
            </Box>
            <Typography variant="caption" color="text.secondary">
              {bar.displayValue}
            </Typography>
          </Box>
        );
      })}
    </Box>
  );
}
