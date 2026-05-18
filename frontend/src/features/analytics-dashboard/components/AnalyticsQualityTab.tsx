import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { Box, Typography } from '@mui/material';
import { pathToAislePositions } from '../../../constants/appRoutes';
import { sortDataTableRows, type DataTableColumn } from '../../../components/ui';
import { MetricsAislesAttentionSection } from '../../analytics/components/MetricsAislesAttentionSection';
import { MetricsManualInterventionSection } from '../../analytics/components/MetricsManualInterventionSection';
import { MetricsQualitySection } from '../../analytics/components/MetricsQualitySection';
import { MetricsResolutionFlowSection } from '../../analytics/components/MetricsResolutionFlowSection';
import { localizeAnalyticsSummaryNote } from '../../analytics/adapters/analyticsSummaryNotes';
import { paginateRows } from '../../analytics/adapters/metricsFormatters';
import {
  buildManualInterventionViewModel,
  buildResolutionFlowStages,
  orderQualityRows,
} from '../../analytics/adapters/metricsViewModel';
import { numberOrZero } from '../../analytics/adapters/metricsFormatters';
import type { AisleIssueRow } from '../../analytics/types';
import type { useAnalyticsDashboard } from '../../analytics/hooks';

type AnalyticsBundle = ReturnType<typeof useAnalyticsDashboard>;

export interface AnalyticsQualityTabProps {
  analytics: AnalyticsBundle;
  isLoading: boolean;
}

export function AnalyticsQualityTab({ analytics, isLoading }: AnalyticsQualityTabProps) {
  const { t } = useTranslation();
  const { summary, quality, manualInterventions, aisleIssues } = analytics;
  const [aisleSearch, setAisleSearch] = useState('');
  const [aislePage, setAislePage] = useState(1);
  const [aislePageSize, setAislePageSize] = useState(10);
  const [aisleSortBy, setAisleSortBy] = useState('pending');
  const [aisleSortDir, setAisleSortDir] = useState<'asc' | 'desc'>('desc');

  const manualInterventionViewModel = useMemo(
    () => buildManualInterventionViewModel(manualInterventions?.items),
    [manualInterventions?.items]
  );
  const qualityRowsOrdered = useMemo(() => orderQualityRows(quality?.items ?? []), [quality?.items]);
  const localizedSummaryNotes = useMemo(
    () => (summary?.notes ?? []).map((n) => localizeAnalyticsSummaryNote(n, t)),
    [summary?.notes, t]
  );

  const pendingReviewCount = useMemo(
    () => (aisleIssues?.items ?? []).reduce((sum, row) => sum + numberOrZero(row.needs_review_count), 0),
    [aisleIssues?.items]
  );

  const totalPositionsCount = summary?.total_positions_in_scope ?? summary?.positions_in_scope ?? 0;
  const processedPositionsCount = summary?.processed_positions_count ?? 0;
  const reviewedPositionsCount = summary?.reviewed_positions_count ?? 0;
  const interventionPositionsCount = manualInterventions?.intervention_positions_count ?? 0;
  const operatorMarkedUnknownCount = summary?.operator_marked_unknown_count ?? summary?.unknown_count ?? 0;

  const resolutionFlowStages = useMemo(
    () =>
      buildResolutionFlowStages(
        {
          totalPositionsCount,
          pendingReviewCount,
          processedPositionsCount,
          reviewedPositionsCount,
          interventionPositionsCount,
          operatorMarkedUnknownCount,
          hasOperatorUnknownRate: (summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null,
        },
        t
      ),
    [
      t,
      totalPositionsCount,
      pendingReviewCount,
      processedPositionsCount,
      reviewedPositionsCount,
      interventionPositionsCount,
      operatorMarkedUnknownCount,
      summary?.operator_marked_unknown_rate,
      summary?.unknown_rate,
    ]
  );

  const aisleColumns = useMemo<DataTableColumn<AisleIssueRow>[]>(
    () => [
      {
        id: 'aisle',
        label: t('common.aisle'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => r.aisle_code,
        cell: (r) => (
          <Typography
            component={RouterLink}
            to={pathToAislePositions(r.inventory_id, r.aisle_id)}
            variant="body2"
            fontWeight={600}
            color="primary"
            sx={{ textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
          >
            {r.aisle_code}
          </Typography>
        ),
      },
      {
        id: 'inventory',
        label: t('analytics.column_inventory'),
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => r.inventory_name,
        cell: (r) => r.inventory_name,
      },
      {
        id: 'pending',
        label: t('analytics.column_pending'),
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (r) => r.needs_review_count,
        cell: (r) => r.needs_review_count,
      },
    ],
    [t]
  );

  const aisleRowsFiltered = useMemo(() => {
    const q = aisleSearch.trim().toLowerCase();
    const items = aisleIssues?.items ?? [];
    if (!q) return items;
    return items.filter(
      (r) =>
        r.aisle_code.toLowerCase().includes(q) ||
        r.inventory_name.toLowerCase().includes(q) ||
        r.most_common_issue?.toLowerCase().includes(q)
    );
  }, [aisleIssues?.items, aisleSearch]);

  const aisleRowsSorted = useMemo(
    () => sortDataTableRows(aisleRowsFiltered, aisleColumns, aisleSortBy, aisleSortDir),
    [aisleRowsFiltered, aisleColumns, aisleSortBy, aisleSortDir]
  );
  const aisleRowsPaged = useMemo(
    () => paginateRows(aisleRowsSorted, aislePage, aislePageSize),
    [aisleRowsSorted, aislePage, aislePageSize]
  );

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' },
        gap: 2,
        minWidth: 0,
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <MetricsManualInterventionSection
          notes={localizedSummaryNotes}
          isLoading={isLoading}
          hasManualInterventions={Boolean(manualInterventions)}
          reviewedPositionsCount={manualInterventions?.reviewed_positions_count ?? 0}
          supportedInterventions={manualInterventionViewModel.orderedSupportedInterventions}
          unsupportedInterventions={manualInterventionViewModel.unsupportedInterventions}
        />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <MetricsResolutionFlowSection
          isLoading={isLoading}
          hasSummary={Boolean(summary)}
          hasOperatorUnknownRate={(summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null}
          resolutionFlowStages={resolutionFlowStages}
          totalPositionsCount={totalPositionsCount}
          manualCorrectionCount={manualInterventionViewModel.manualCorrectionCount}
          operatorMarkedUnknownCount={operatorMarkedUnknownCount}
        />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <MetricsQualitySection isLoading={isLoading} hasQualityData={Boolean(quality)} rows={qualityRowsOrdered} />
      </Box>
      <Box sx={{ minWidth: 0, gridColumn: { xs: '1', md: '1 / -1' } }}>
        <MetricsAislesAttentionSection
          search={aisleSearch}
          onSearchChange={(value) => {
            setAisleSearch(value);
            setAislePage(1);
          }}
          onResetSearch={() => {
            setAisleSearch('');
            setAislePage(1);
          }}
          rows={aisleRowsPaged}
          columns={aisleColumns}
          isLoading={isLoading}
          sortBy={aisleSortBy}
          sortDir={aisleSortDir}
          onSortChange={(sortBy, sortDir) => {
            setAisleSortBy(sortBy);
            setAisleSortDir(sortDir);
            setAislePage(1);
          }}
          page={aislePage}
          pageSize={aislePageSize}
          totalItems={aisleRowsSorted.length}
          onPageChange={setAislePage}
          onPageSizeChange={setAislePageSize}
        />
      </Box>
    </Box>
  );
}
