/**
 * Operational analytics dashboard focused on efficiency, manual effort, and quality hotspots.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import {
  pathToAislePositions,
  pathToInventory,
  pathToInventoryAnalyticsCompare,
} from '../../constants/appRoutes';
import {
  Alert,
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  ErrorAlert,
  FilterToolbar,
  type DataTableColumn,
} from '../../components/ui';
import { PageHeader } from '../../components/shell';
import { useInventoriesList } from '../../hooks/useInventories';
import { useAislesList } from '../../hooks/useAisles';
import { formatDate } from '../../utils/formatDate';
import { rowMatchesSearchQuery } from '../../utils/tableSearch';
import i18n from '../../i18n';
import { useAnalyticsDashboard } from './hooks';
import { MetricsAislesAttentionSection } from './components/MetricsAislesAttentionSection';
import { MetricsInventoryPerformanceSection } from './components/MetricsInventoryPerformanceSection';
import { MetricsKpiSection } from './components/MetricsKpiSection';
import { MetricsManualInterventionSection } from './components/MetricsManualInterventionSection';
import { MetricsQualitySection } from './components/MetricsQualitySection';
import { MetricsResolutionFlowSection } from './components/MetricsResolutionFlowSection';
import {
  defaultDateRange,
  formatAvgProcessingMinutes,
  formatPct,
  numberOrZero,
  paginateRows,
} from './adapters/metricsFormatters';
import {
  buildManualInterventionViewModel,
  buildMetricsKpiCards,
  buildResolutionFlowStages,
  buildScopeSummary,
  orderQualityRows,
  sortAisleRowsByAttention,
  sortInventoryRows,
} from './adapters/metricsViewModel';
import type {
  AnalyticsQueryParams,
  InventoryPerformanceRow,
  AisleIssueRow,
} from './types';

export default function MetricsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const initial = useMemo(() => defaultDateRange(), []);
  const [dateFrom, setDateFrom] = useState(initial.from);
  const [dateTo, setDateTo] = useState(initial.to);
  const [inventoryId, setInventoryId] = useState<string>('');
  const [aisleId, setAisleId] = useState<string>('');

  const params: AnalyticsQueryParams = useMemo(
    () => ({
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      inventory_id: inventoryId || undefined,
      aisle_id: aisleId || undefined,
    }),
    [dateFrom, dateTo, inventoryId, aisleId]
  );

  const inventoriesQuery = useInventoriesList({ page: 1, page_size: 200, sort_by: 'name', sort_dir: 'asc' });
  const invList = inventoriesQuery.data;
  const inventories = invList?.items ?? [];

  const aislesQuery = useAislesList(inventoryId || undefined, { enabled: Boolean(inventoryId) });
  const aisles = aislesQuery.data?.items ?? [];
  const effectiveAisleId = aisleId && aisles.some((aisle) => aisle.id === aisleId) ? aisleId : '';
  const selectedInventory = inventories.find((inv) => inv.id === inventoryId) ?? null;
  const selectedAisle = aisles.find((aisle) => aisle.id === effectiveAisleId) ?? null;
  const compareRunsHref =
    inventoryId && selectedInventory && selectedInventory.processing_mode === 'test'
      ? pathToInventoryAnalyticsCompare(inventoryId)
      : null;
  const compareRunsDisabledReason = compareRunsHref
    ? ''
    : !inventoryId
      ? t('analytics.compare_runs_metrics_select_inventory')
      : t('analytics.compare_runs_metrics_test_only');

  const [inventoryPage, setInventoryPage] = useState(1);
  const [inventoryPageSize, setInventoryPageSize] = useState(10);
  const [inventorySortBy, setInventorySortBy] = useState('auto_accept');
  const [inventorySortDir, setInventorySortDir] = useState<'asc' | 'desc'>('desc');
  const [aislePage, setAislePage] = useState(1);
  const [aislePageSize, setAislePageSize] = useState(10);
  const [perfTableSearch, setPerfTableSearch] = useState('');
  const [aisleMetricsTableSearch, setAisleMetricsTableSearch] = useState('');

  const {
    summary,
    inventoryPerformance,
    aisleIssues,
    quality,
    manualInterventions,
    isLoading,
    isError,
    errors,
    refetchAll,
  } =
    useAnalyticsDashboard(params);

  const firstAnalyticsError = isError && errors[0] ? errors[0] : null;

  const inventoryRowsFiltered = useMemo(() => {
    const items = inventoryPerformance?.items ?? [];
    return items.filter((r) =>
      rowMatchesSearchQuery(perfTableSearch, [
        r.inventory_name,
        r.inventory_id,
        String(r.total_positions ?? r.positions_count ?? ''),
      ])
    );
  }, [inventoryPerformance?.items, perfTableSearch]);

  const inventoryRowsSorted = useMemo(
    () => sortInventoryRows(inventoryRowsFiltered, inventorySortBy, inventorySortDir),
    [inventoryRowsFiltered, inventorySortBy, inventorySortDir]
  );
  const maxInventoryPage = Math.max(1, Math.ceil(Math.max(inventoryRowsSorted.length, 1) / inventoryPageSize));
  const effectiveInventoryPage = Math.min(inventoryPage, maxInventoryPage);
  const inventoryRowsPaged = useMemo(
    () => paginateRows(inventoryRowsSorted, effectiveInventoryPage, inventoryPageSize),
    [inventoryRowsSorted, effectiveInventoryPage, inventoryPageSize]
  );
  const aisleRowsFiltered = useMemo(() => {
    const items = aisleIssues?.items ?? [];
    return items.filter((r) =>
      rowMatchesSearchQuery(aisleMetricsTableSearch, [
        r.aisle_code,
        r.inventory_name,
        r.aisle_id,
        r.most_common_issue,
      ])
    );
  }, [aisleIssues?.items, aisleMetricsTableSearch]);

  const aisleRowsSorted = useMemo(
    () => sortAisleRowsByAttention(aisleRowsFiltered),
    [aisleRowsFiltered]
  );
  const maxAislePage = Math.max(1, Math.ceil(Math.max(aisleRowsSorted.length, 1) / aislePageSize));
  const effectiveAislePage = Math.min(aislePage, maxAislePage);
  const aisleRowsPaged = useMemo(
    () => paginateRows(aisleRowsSorted, effectiveAislePage, aislePageSize),
    [aisleRowsSorted, effectiveAislePage, aislePageSize]
  );

  const qualityRowsOrdered = useMemo(() => orderQualityRows(quality?.items ?? []), [quality?.items]);
  const manualInterventionViewModel = useMemo(
    () => buildManualInterventionViewModel(manualInterventions?.items),
    [manualInterventions?.items]
  );
  const { unsupportedInterventions, orderedSupportedInterventions, manualCorrectionCount } = manualInterventionViewModel;
  const pendingReviewCount = useMemo(
    () => (aisleIssues?.items ?? []).reduce((sum, row) => sum + numberOrZero(row.needs_review_count), 0),
    [aisleIssues?.items]
  );
  const hasUnidentifiedProductRate = summary?.unidentified_product_rate != null;
  const operatorMarkedUnknownCount = summary?.operator_marked_unknown_count ?? summary?.unknown_count ?? 0;
  const totalPositionsCount = summary?.total_positions_in_scope ?? summary?.positions_in_scope ?? 0;
  const processedPositionsCount = summary?.processed_positions_count ?? 0;
  const reviewedPositionsCount = summary?.reviewed_positions_count ?? 0;
  const interventionPositionsCount = manualInterventions?.intervention_positions_count ?? 0;
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

  const invColumns = useMemo<DataTableColumn<InventoryPerformanceRow>[]>(
    () => [
      {
        id: 'name',
        label: t('analytics.column_inventory'),
        sortable: false,
        cell: (r) => (
          <Typography
            component={RouterLink}
            to={pathToInventory(r.inventory_id)}
            variant="body2"
            fontWeight={600}
            color="primary"
            sx={{ textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
          >
            {r.inventory_name}
          </Typography>
        ),
      },
      {
        id: 'created',
        label: t('common.created'),
        cell: (r) => formatDate(r.inventory_created_at),
        sortable: true,
      },
      {
        id: 'aisles',
        label: t('inventory.column_aisles'),
        align: 'right',
        sortable: true,
        cell: (r) => r.aisles_count ?? r.total_aisles,
      },
      {
        id: 'positions',
        label: t('analytics.column_positions'),
        align: 'right',
        sortable: true,
        cell: (r) => r.positions_count ?? r.total_positions,
      },
      {
        id: 'processed',
        label: t('analytics.column_processed'),
        align: 'right',
        sortable: true,
        cell: (r) => r.processed_count ?? r.processed_positions,
      },
      {
        id: 'auto_accept',
        label: t('analytics.column_auto_accept'),
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.auto_acceptance_rate),
      },
      {
        id: 'manual_correction',
        label: t('analytics.column_manual_correction'),
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.manual_correction_rate ?? r.correction_rate),
      },
      ...(hasUnidentifiedProductRate
        ? [
            {
              id: 'unidentified_product',
              label: t('analytics.column_unidentified_product'),
              align: 'right' as const,
              sortable: true,
              cell: (r: InventoryPerformanceRow) => formatPct(r.unidentified_product_rate),
            },
          ]
        : []),
      {
        id: 'invalid_tr',
        label: t('analytics.column_invalid_tr'),
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.invalid_traceability_rate),
      },
      {
        id: 'avg_conf',
        label: t('analytics.column_avg_confidence'),
        align: 'right',
        sortable: true,
        cell: (r) =>
          r.avg_confidence != null ? `${(r.avg_confidence * 100).toFixed(0)}%` : i18n.t('common.em_dash'),
      },
      {
        id: 'avg_processing',
        label: t('analytics.column_avg_processing'),
        align: 'right',
        sortable: true,
        cell: (r) => formatAvgProcessingMinutes(r.average_processing_time_minutes, null),
      },
      {
        id: 'proc',
        label: t('analytics.column_job_success'),
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.processing_success_rate),
      },
    ],
    [hasUnidentifiedProductRate, t]
  );

  const aisleColumns = useMemo<DataTableColumn<AisleIssueRow>[]>(
    () => [
      {
        id: 'aisle',
        label: t('common.aisle'),
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
        cell: (r) => (
          <Typography variant="body2" color="text.secondary">
            {r.inventory_name}
          </Typography>
        ),
      },
      { id: 'total', label: t('analytics.column_total'), align: 'right', cell: (r) => r.total_results },
      { id: 'pending', label: t('analytics.column_pending'), align: 'right', cell: (r) => r.needs_review_count },
      {
        id: 'unidentified_product',
        label: t('analytics.column_unidentified_count'),
        align: 'right',
        cell: (r) => r.unidentified_product_count ?? 0,
      },
      {
        id: 'inv_tr',
        label: t('analytics.column_inv_tr'),
        align: 'right',
        cell: (r) => r.invalid_traceability_count,
      },
      {
        id: 'manual_c',
        label: t('analytics.column_manual_corrections'),
        align: 'right',
        cell: (r) => r.manual_corrections_count ?? r.corrected_count,
      },
    ],
    [t]
  );

  const kpiCards = useMemo(
    () => buildMetricsKpiCards(summary, hasUnidentifiedProductRate, t),
    [hasUnidentifiedProductRate, summary, t]
  );

  const scopeSummary = useMemo(
    () =>
      buildScopeSummary(
        {
          summary,
          selectedInventoryName: selectedInventory?.name ?? null,
          selectedAisleCode: selectedAisle?.code ?? null,
          hasInventorySelected: Boolean(inventoryId),
        },
        t
      ),
    [summary, selectedInventory, selectedAisle, inventoryId, t]
  );

  return (
    <Box sx={{ pb: 4, width: '100%', minWidth: 0, maxWidth: '100%', overflowX: 'hidden', boxSizing: 'border-box' }}>
      {firstAnalyticsError ? (
        <ErrorAlert error={firstAnalyticsError} context="analytics" onRetry={() => refetchAll()} />
      ) : null}

      <PageHeader a11yTitle={t('analytics.page_a11y')} />

      <FilterToolbar
        onReset={() => {
          const d = defaultDateRange();
          setDateFrom(d.from);
          setDateTo(d.to);
          setInventoryId('');
          setAisleId('');
          setInventoryPage(1);
          setAislePage(1);
        }}
        endActions={
          <>
            <Tooltip
              title={compareRunsDisabledReason}
              disableHoverListener={Boolean(compareRunsHref)}
            >
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  data-testid="metrics-compare-runs"
                  disabled={!compareRunsHref}
                  onClick={() => compareRunsHref && navigate(compareRunsHref)}
                >
                  {t('analytics.compare_runs_link')}
                </Button>
              </span>
            </Tooltip>
            <Button size="small" variant="outlined" onClick={() => refetchAll()} disabled={isLoading}>
              {t('common.refresh')}
            </Button>
          </>
        }
      >
        <TextField
          size="small"
          label={t('common.from')}
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 150 }}
        />
        <TextField
          size="small"
          label={t('common.to')}
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 150 }}
        />
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="metrics-inv-label">{t('common.inventory')}</InputLabel>
          <Select
            labelId="metrics-inv-label"
            label={t('common.inventory')}
            value={inventoryId}
            onChange={(e) => {
              setInventoryId(e.target.value);
              setAisleId('');
            }}
          >
            <MenuItem value="">{t('analytics.scope_inventory_all')}</MenuItem>
            {inventories.map((inv) => (
              <MenuItem key={inv.id} value={inv.id}>
                {inv.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 180 }} disabled={!inventoryId}>
          <InputLabel id="metrics-aisle-label">{t('common.aisle')}</InputLabel>
          <Select
            labelId="metrics-aisle-label"
            label={t('common.aisle')}
            value={effectiveAisleId}
            onChange={(e) => setAisleId(e.target.value)}
          >
            <MenuItem value="">{t('analytics.all_aisles_option')}</MenuItem>
            {aisles.map((a) => (
              <MenuItem key={a.id} value={a.id}>
                {a.code}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </FilterToolbar>

      {inventoriesQuery.isError ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('analytics.filter_options_load_failed')}
        </Alert>
      ) : null}

      {scopeSummary ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('analytics.scope_summary', {
            inventory: scopeSummary.inventoryLabel,
            aisle: scopeSummary.aisleLabel,
            positions: scopeSummary.positions,
          })}
        </Typography>
      ) : null}

      <MetricsKpiSection
        cards={kpiCards}
        isLoading={isLoading}
        hasSummary={Boolean(summary)}
        skeletonCount={hasUnidentifiedProductRate ? 6 : 5}
      />

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' },
          gap: 2,
          mb: 2,
          minWidth: 0,
          width: '100%',
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <MetricsManualInterventionSection
            notes={summary?.notes ?? []}
            isLoading={isLoading}
            hasManualInterventions={Boolean(manualInterventions)}
            reviewedPositionsCount={manualInterventions?.reviewed_positions_count ?? 0}
            supportedInterventions={orderedSupportedInterventions}
            unsupportedInterventions={unsupportedInterventions}
          />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <MetricsResolutionFlowSection
            isLoading={isLoading}
            hasSummary={Boolean(summary)}
            hasOperatorUnknownRate={(summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null}
            resolutionFlowStages={resolutionFlowStages}
            totalPositionsCount={totalPositionsCount}
            manualCorrectionCount={manualCorrectionCount}
            operatorMarkedUnknownCount={operatorMarkedUnknownCount}
          />
        </Box>
      </Box>

      <MetricsInventoryPerformanceSection
        search={perfTableSearch}
        onSearchChange={(value) => {
          setPerfTableSearch(value);
          setInventoryPage(1);
        }}
        onResetSearch={() => {
          setPerfTableSearch('');
          setInventoryPage(1);
        }}
        rows={inventoryRowsPaged}
        columns={invColumns}
        isLoading={isLoading}
        sortBy={inventorySortBy}
        sortDir={inventorySortDir}
        onSortChange={(sortBy, sortDir) => {
          setInventorySortBy(sortBy);
          setInventorySortDir(sortDir);
          setInventoryPage(1);
        }}
        page={effectiveInventoryPage}
        pageSize={inventoryPageSize}
        totalItems={inventoryRowsSorted.length}
        onPageChange={setInventoryPage}
        onPageSizeChange={setInventoryPageSize}
      />

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' },
          gap: 2,
          mb: 2,
          minWidth: 0,
          width: '100%',
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <MetricsQualitySection isLoading={isLoading} hasQualityData={Boolean(quality)} rows={qualityRowsOrdered} />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <MetricsAislesAttentionSection
            search={aisleMetricsTableSearch}
            onSearchChange={(value) => {
              setAisleMetricsTableSearch(value);
              setAislePage(1);
            }}
            onResetSearch={() => {
              setAisleMetricsTableSearch('');
              setAislePage(1);
            }}
            rows={aisleRowsPaged}
            columns={aisleColumns}
            isLoading={isLoading}
            page={effectiveAislePage}
            pageSize={aislePageSize}
            totalItems={aisleRowsSorted.length}
            onPageChange={setAislePage}
            onPageSizeChange={setAislePageSize}
          />
        </Box>
      </Box>
    </Box>
  );
}
