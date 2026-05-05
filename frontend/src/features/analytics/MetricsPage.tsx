/**
 * Operational analytics dashboard focused on efficiency, manual effort, and quality hotspots.
 */

import { useEffect, useMemo, useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import {
  pathToAislePositions,
  pathToInventory,
  pathToInventoryAnalyticsCompare,
} from '../../constants/appRoutes';
import {
  Alert,
  Chip,
  Box,
  Button,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Skeleton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  DataTable,
  ErrorAlert,
  FilterToolbar,
  KpiCard,
  SectionCard,
  TableSearchField,
  type DataTableColumn,
} from '../../components/ui';
import { PageHeader } from '../../components/shell';
import { useInventoriesList } from '../../hooks/useInventories';
import { useAislesList } from '../../hooks/useAisles';
import { formatDate } from '../../utils/formatDate';
import { rowMatchesSearchQuery } from '../../utils/tableSearch';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import { ApiError } from '../../api/types';
import i18n from '../../i18n';
import { useAnalyticsDashboard } from './hooks';
import type {
  AnalyticsQueryParams,
  InventoryPerformanceRow,
  AisleIssueRow,
  QualityPatternRow,
  ManualInterventionCategory,
} from './types';

function defaultDateRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - 30);
  return { from: from.toISOString().slice(0, 10), to: to.toISOString().slice(0, 10) };
}

function formatPct(x: number | null | undefined): string {
  if (x == null || Number.isNaN(x)) return i18n.t('common.em_dash');
  return `${(x * 100).toFixed(1)}%`;
}

function formatAvgProcessingSec(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return i18n.t('common.em_dash');
  if (sec < 60) return `${Math.round(sec)}s`;
  return `${(sec / 60).toFixed(1)} min`;
}

/** Job duration KPI: prefer minutes from API; fall back to raw seconds. */
function formatAvgProcessingMinutes(minutes: number | null | undefined, seconds: number | null | undefined): string {
  if (minutes != null && !Number.isNaN(minutes)) return `${minutes.toFixed(1)} min`;
  return formatAvgProcessingSec(seconds);
}

function numberOrZero(value: number | null | undefined): number {
  return value ?? 0;
}

function paginateRows<T>(rows: readonly T[], page: number, pageSize: number): readonly T[] {
  const start = (page - 1) * pageSize;
  return rows.slice(start, start + pageSize);
}

function compareValues(a: number | string | null | undefined, b: number | string | null | undefined): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

function sortInventoryRows(
  rows: readonly InventoryPerformanceRow[],
  sortBy: string,
  sortDir: 'asc' | 'desc'
): InventoryPerformanceRow[] {
  const direction = sortDir === 'asc' ? 1 : -1;
  const getValue = (row: InventoryPerformanceRow): number | string | null | undefined => {
    switch (sortBy) {
      case 'created':
        return row.inventory_created_at;
      case 'aisles':
        return row.aisles_count ?? row.total_aisles;
      case 'positions':
        return row.positions_count ?? row.total_positions;
      case 'processed':
        return row.processed_count ?? row.processed_positions;
      case 'auto_accept':
        return row.auto_acceptance_rate ?? null;
      case 'manual_correction':
        return row.manual_correction_rate ?? row.correction_rate;
      case 'unidentified_product':
        return row.unidentified_product_rate ?? null;
      case 'invalid_tr':
        return row.invalid_traceability_rate;
      case 'avg_conf':
        return row.avg_confidence;
      case 'avg_processing':
        return row.average_processing_time_minutes ?? null;
      case 'proc':
        return row.processing_success_rate;
      case 'name':
      default:
        return row.inventory_name;
    }
  };
  return [...rows].sort((left, right) => {
    const result = compareValues(getValue(left), getValue(right));
    if (result !== 0) return result * direction;
    return left.inventory_name.localeCompare(right.inventory_name) * direction;
  });
}

function qualityPriority(label: string): number {
  const normalized = label.trim().toLowerCase();
  if (normalized === 'unidentified product') return 0;
  if (normalized === 'pending review') return 1;
  if (normalized === 'invalid traceability') return 2;
  if (normalized === 'missing evidence') return 3;
  if (normalized.includes('zero')) return 4;
  if (normalized === 'low confidence') return 5;
  if (normalized === 'no primary issue') return 6;
  return 50;
}

function interventionLabel(category: string, t: TFunction): string {
  switch (category) {
    case 'confirmed':
      return t('analytics.category_confirmed');
    case 'qty_corrected':
      return t('analytics.category_qty_corrected');
    case 'sku_corrected':
      return t('analytics.category_sku_corrected');
    case 'invalid':
      return t('analytics.category_invalid');
    case 'operator_marked_unknown':
      return t('analytics.category_operator_unknown');
    case 'deleted':
      return t('analytics.category_deleted');
    default:
      return category;
  }
}

function interventionPriority(category: string): number {
  switch (category) {
    case 'operator_marked_unknown':
      return 0;
    case 'qty_corrected':
      return 1;
    case 'sku_corrected':
      return 2;
    case 'confirmed':
      return 3;
    case 'deleted':
      return 4;
    case 'invalid':
      return 5;
    default:
      return 50;
  }
}

function interventionColor(category: string): string {
  switch (category) {
    case 'operator_marked_unknown':
      return 'warning.main';
    case 'qty_corrected':
    case 'sku_corrected':
      return 'secondary.main';
    case 'confirmed':
      return 'success.main';
    case 'deleted':
      return 'text.secondary';
    default:
      return 'primary.main';
  }
}

function translateQualityIssueType(issueType: string, t: TFunction): string {
  const slug = issueType
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  const key = `analytics.quality_issue.${slug}`;
  const translated = t(key);
  return translated === key ? issueType : translated;
}

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
  const selectedInventory = inventories.find((inv) => inv.id === inventoryId) ?? null;
  const selectedAisle = aisles.find((aisle) => aisle.id === aisleId) ?? null;
  const compareRunsHref =
    Boolean(inventoryId && selectedInventory && selectedInventory.processing_mode === 'test')
      ? pathToInventoryAnalyticsCompare(inventoryId)
      : null;
  const compareRunsDisabledReason = compareRunsHref
    ? ''
    : !inventoryId
      ? t('analytics.compare_runs_metrics_select_inventory')
      : t('analytics.compare_runs_metrics_test_only');

  useEffect(() => {
    if (aisleId && !aisles.some((aisle) => aisle.id === aisleId)) {
      queueMicrotask(() => setAisleId(''));
    }
  }, [aisleId, aisles]);

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

  const errMsg =
    isError && errors[0]
      ? errors[0] instanceof ApiError
        ? resolveApiErrorMessage(errors[0], 'errors.load_metrics')
        : String(errors[0])
      : null;

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
  const inventoryRowsPaged = useMemo(
    () => paginateRows(inventoryRowsSorted, inventoryPage, inventoryPageSize),
    [inventoryRowsSorted, inventoryPage, inventoryPageSize]
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
    () =>
      [...aisleRowsFiltered].sort(
        (left, right) =>
          (numberOrZero(right.needs_review_count) +
            numberOrZero(right.unidentified_product_count ?? right.unknown_count) +
            numberOrZero(right.manual_corrections_count ?? right.corrected_count) +
            numberOrZero(right.invalid_traceability_count)) -
            (numberOrZero(left.needs_review_count) +
              numberOrZero(left.unidentified_product_count ?? left.unknown_count) +
              numberOrZero(left.manual_corrections_count ?? left.corrected_count) +
              numberOrZero(left.invalid_traceability_count)) ||
          numberOrZero(right.needs_review_count) - numberOrZero(left.needs_review_count) ||
          numberOrZero(right.total_results) - numberOrZero(left.total_results)
      ),
    [aisleRowsFiltered]
  );
  const aisleRowsPaged = useMemo(
    () => paginateRows(aisleRowsSorted, aislePage, aislePageSize),
    [aisleRowsSorted, aislePage, aislePageSize]
  );

  useEffect(() => {
    queueMicrotask(() => setInventoryPage(1));
  }, [perfTableSearch]);

  useEffect(() => {
    queueMicrotask(() => setAislePage(1));
  }, [aisleMetricsTableSearch]);

  const qualityRowsOrdered = useMemo(
    () =>
      [...(quality?.items ?? [])].sort(
        (left, right) =>
          qualityPriority(left.issue_type) - qualityPriority(right.issue_type) ||
          numberOrZero(right.count) - numberOrZero(left.count)
      ),
    [quality?.items]
  );
  const supportedInterventions = useMemo(
    () =>
      (manualInterventions?.items ?? []).filter(
        (item: ManualInterventionCategory) => item.available && (item.count ?? 0) > 0
      ),
    [manualInterventions?.items]
  );
  const unsupportedInterventions = useMemo(
    () => (manualInterventions?.items ?? []).filter((item: ManualInterventionCategory) => !item.available),
    [manualInterventions?.items]
  );
  const orderedSupportedInterventions = useMemo(
    () =>
      [...supportedInterventions].sort(
        (left, right) =>
          interventionPriority(left.category) - interventionPriority(right.category) ||
          numberOrZero(right.count) - numberOrZero(left.count)
      ),
    [supportedInterventions]
  );
  const manualCorrectionCount = useMemo(
    () =>
      numberOrZero(
        manualInterventions?.items?.find((item: ManualInterventionCategory) => item.category === 'qty_corrected')?.count
      ) +
      numberOrZero(
        manualInterventions?.items?.find((item: ManualInterventionCategory) => item.category === 'sku_corrected')?.count
      ),
    [manualInterventions?.items]
  );
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
    () => [
      {
        label: t('analytics.positions_in_scope'),
        value: totalPositionsCount,
        helper: t('analytics.positions_in_scope_help'),
      },
      {
        label: t('analytics.pending_review'),
        value: pendingReviewCount,
        helper: t('analytics.pending_review_help'),
      },
      {
        label: t('analytics.processed'),
        value: processedPositionsCount,
        helper: t('analytics.processed_help'),
      },
      {
        label: t('analytics.reviewed'),
        value: reviewedPositionsCount,
        helper: t('analytics.reviewed_help'),
      },
      {
        label: t('analytics.manual_touch'),
        value: interventionPositionsCount,
        helper: t('analytics.manual_touch_help'),
      },
      ...((summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null
        ? [
            {
              label: t('analytics.operator_unknown'),
              value: operatorMarkedUnknownCount,
              helper: t('analytics.operator_unknown_help'),
            },
          ]
        : []),
    ],
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
    () => [
      {
        label: t('analytics.kpi_auto_accept_title'),
        value: formatPct(summary?.auto_acceptance_rate),
        description: summary?.reviewed_positions_count
          ? t('analytics.kpi_fraction_reviewed', {
              numerator: Math.round((summary.auto_acceptance_rate ?? 0) * summary.reviewed_positions_count),
              denominator: summary.reviewed_positions_count,
            })
          : t('analytics.kpi_auto_accept_desc'),
      },
      {
        label: t('analytics.kpi_manual_correction_title'),
        value: formatPct(summary?.manual_correction_rate),
        description: summary?.reviewed_positions_count
          ? t('analytics.kpi_fraction_reviewed', {
              numerator: Math.round((summary.manual_correction_rate ?? 0) * summary.reviewed_positions_count),
              denominator: summary.reviewed_positions_count,
            })
          : t('analytics.kpi_manual_correction_desc'),
      },
      ...(hasUnidentifiedProductRate
        ? [
            {
              label: t('analytics.kpi_unidentified_title'),
              value: formatPct(summary?.unidentified_product_rate),
              description:
                summary?.unidentified_product_count != null && summary?.total_positions_in_scope
                  ? t('analytics.kpi_fraction_scope', {
                      numerator: summary.unidentified_product_count,
                      denominator: summary.total_positions_in_scope,
                    })
                  : t('analytics.kpi_unidentified_desc'),
            },
          ]
        : []),
      {
        label: t('analytics.kpi_processing_success_title'),
        value: formatPct(summary?.processing_success_rate),
        description: t('analytics.kpi_processing_success_desc'),
      },
      {
        label: t('analytics.kpi_avg_processing_title'),
        value: formatAvgProcessingMinutes(
          summary?.average_processing_time_minutes,
          summary?.average_processing_time_seconds
        ),
        description: t('analytics.kpi_avg_processing_desc'),
      },
      {
        label: t('analytics.kpi_invalid_tr_title'),
        value: formatPct(summary?.invalid_traceability_rate),
        description: summary?.total_positions_in_scope
          ? t('analytics.kpi_fraction_scope', {
              numerator: Math.round((summary.invalid_traceability_rate ?? 0) * summary.total_positions_in_scope),
              denominator: summary.total_positions_in_scope,
            })
          : t('analytics.kpi_invalid_tr_desc'),
      },
    ],
    [hasUnidentifiedProductRate, summary, t]
  );

  const scopeSummary = useMemo(
    () =>
      summary
        ? {
            inventoryLabel: selectedInventory ? selectedInventory.name : t('analytics.scope_inventory_all'),
            aisleLabel: selectedAisle
              ? selectedAisle.code
              : inventoryId
                ? t('analytics.scope_aisle_inventory')
                : t('analytics.scope_aisle_all'),
            positions: summary.total_positions_in_scope ?? summary.positions_in_scope,
          }
        : null,
    [summary, selectedInventory, selectedAisle, inventoryId, t]
  );

  return (
    <Box sx={{ pb: 4, width: '100%', minWidth: 0, maxWidth: '100%', overflowX: 'hidden', boxSizing: 'border-box' }}>
      {errMsg ? <ErrorAlert message={errMsg} onRetry={() => refetchAll()} /> : null}

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
            value={aisleId}
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

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: {
            xs: 'minmax(0, 1fr)',
            sm: 'repeat(2, minmax(0, 1fr))',
            md: 'repeat(3, minmax(0, 1fr))',
          },
          gap: 2,
          mb: 2,
          minWidth: 0,
          width: '100%',
        }}
      >
        {isLoading && !summary
          ? Array.from({ length: hasUnidentifiedProductRate ? 6 : 5 }).map((_, i) => (
              <Skeleton key={`sk-${i}`} variant="rounded" height={100} sx={{ minWidth: 0 }} />
            ))
          : kpiCards.map((k) => (
              <Box key={k.label} sx={{ minWidth: 0 }}>
                <KpiCard label={k.label} value={k.value} description={k.description} />
              </Box>
            ))}
      </Box>

      {summary?.notes?.length ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {summary.notes.join(' ')}
        </Alert>
      ) : null}

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
          <SectionCard
            title={t('analytics.manual_intervention_title')}
            subtitle={t('analytics.manual_intervention_subtitle')}
          >
            {isLoading && !manualInterventions ? (
              <Skeleton variant="rounded" height={220} />
            ) : supportedInterventions.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('analytics.no_manual_interventions_scope')}
              </Typography>
            ) : (
              <Stack spacing={1.5}>
                <Box
                  sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 2,
                    flexWrap: 'wrap',
                    p: 1.5,
                    border: 1,
                    borderColor: 'divider',
                    borderRadius: 1.5,
                    bgcolor: 'background.default',
                  }}
                >
                  <Typography variant="body2" color="text.secondary">
                    {t('analytics.reviewed_positions_label')}
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {manualInterventions?.reviewed_positions_count ?? 0}
                  </Typography>
                </Box>
                {orderedSupportedInterventions.map((item: ManualInterventionCategory) => (
                  <Box key={item.category}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, mb: 0.5 }}>
                      <Typography variant="body2" fontWeight={600}>
                        {interventionLabel(item.category, t)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                        {item.count ?? 0}
                        {item.percentage != null ? ` · ${(item.percentage * 100).toFixed(1)}%` : ''}
                      </Typography>
                    </Box>
                    <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
                      <Box
                        sx={{
                          height: '100%',
                          width: `${Math.min(100, (item.percentage ?? 0) * 100)}%`,
                          bgcolor: interventionColor(item.category),
                        }}
                      />
                    </Box>
                    {item.notes ? (
                      <Typography variant="caption" color="text.secondary">
                        {item.notes}
                      </Typography>
                    ) : null}
                  </Box>
                ))}
                {unsupportedInterventions.length ? (
                  <>
                    <Divider />
                    <Typography variant="caption" color="text.secondary">
                      {t('analytics.awaiting_backend_support')}
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {unsupportedInterventions.map((item: ManualInterventionCategory) => (
                        <Chip
                          key={item.category}
                          label={t('analytics.intervention_unavailable_chip', {
                            label: interventionLabel(item.category, t),
                          })}
                          size="small"
                          variant="outlined"
                        />
                      ))}
                    </Stack>
                  </>
                ) : null}
              </Stack>
            )}
          </SectionCard>
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <SectionCard
            title={t('analytics.resolution_flow_title')}
            subtitle={t('analytics.resolution_flow_subtitle')}
          >
            {isLoading && !summary ? (
              <Skeleton variant="rounded" height={220} />
            ) : (
              <Stack spacing={1.25}>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: {
                      xs: 'repeat(2, minmax(0, 1fr))',
                      md:
                        (summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null
                          ? 'repeat(3, minmax(0, 1fr))'
                          : 'repeat(4, minmax(0, 1fr))',
                    },
                    gap: 1.5,
                    minWidth: 0,
                    width: '100%',
                  }}
                >
                  {resolutionFlowStages.map((item) => (
                    <Box key={item.label} sx={{ minWidth: 0 }}>
                      <Box
                        sx={{
                          border: 1,
                          borderColor: 'divider',
                          borderRadius: 1.5,
                          p: 1.5,
                          height: '100%',
                          bgcolor: 'background.default',
                        }}
                      >
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                          {item.label}
                        </Typography>
                        <Typography variant="h6" sx={{ fontWeight: 700 }}>
                          {item.value}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {item.helper}
                        </Typography>
                      </Box>
                    </Box>
                  ))}
                </Box>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: `repeat(${resolutionFlowStages.length}, minmax(0, 1fr))`,
                    gap: 1,
                  }}
                >
                  {resolutionFlowStages.map((item, index) => (
                    <Box
                      key={`${item.label}-bar`}
                      sx={{
                        minWidth: 0,
                      }}
                    >
                      <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                        {index < resolutionFlowStages.length - 1
                          ? t('analytics.resolution_step')
                          : t('analytics.resolution_outcome')}
                      </Typography>
                      <Box sx={{ height: 10, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
                        <Box
                          sx={{
                            height: '100%',
                            width: `${totalPositionsCount > 0 ? Math.min(100, (item.value / totalPositionsCount) * 100) : 0}%`,
                            bgcolor:
                              index === resolutionFlowStages.length - 1 &&
                              (summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null
                                ? 'warning.main'
                                : 'primary.main',
                          }}
                        />
                      </Box>
                    </Box>
                  ))}
                </Box>
                <Typography variant="caption" color="text.secondary">
                  {t('analytics.manual_corrections_in_scope', { count: manualCorrectionCount })}
                  {(summary?.operator_marked_unknown_rate ?? summary?.unknown_rate) != null
                    ? t('analytics.operator_unknown_outcomes', { count: operatorMarkedUnknownCount })
                    : ''}
                </Typography>
              </Stack>
            )}
          </SectionCard>
        </Box>
      </Box>

      <SectionCard
        title={t('analytics.inventory_performance_title')}
        subtitle={t('analytics.inventory_performance_subtitle')}
      >
        <FilterToolbar
          onReset={() => setPerfTableSearch('')}
          resetDisabled={!perfTableSearch.trim()}
        >
          <TableSearchField
            label={t('table.search_label')}
            placeholder={t('analytics.search_inventory_performance_placeholder')}
            value={perfTableSearch}
            onChange={setPerfTableSearch}
            data-testid="metrics-inventory-performance-search"
          />
        </FilterToolbar>
        <DataTable<InventoryPerformanceRow>
          rows={inventoryRowsPaged}
          rowKey={(r) => r.inventory_id}
          columns={invColumns}
          loading={isLoading}
          sort={{
            sortBy: inventorySortBy,
            sortDir: inventorySortDir,
            onSortChange: (sortBy, sortDir) => {
              setInventorySortBy(sortBy);
              setInventorySortDir(sortDir);
              setInventoryPage(1);
            },
          }}
          pagination={{
            page: inventoryPage,
            pageSize: inventoryPageSize,
            totalItems: inventoryRowsSorted.length,
            onPageChange: setInventoryPage,
            onPageSizeChange: setInventoryPageSize,
          }}
          emptyState={
            perfTableSearch.trim() && !isLoading && inventoryRowsSorted.length === 0
              ? { message: t('table.empty_no_match') }
              : { message: t('analytics.empty_inventory_performance') }
          }
        />
      </SectionCard>

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
          <SectionCard
            title={t('analytics.quality_patterns_title')}
            subtitle={t('analytics.quality_patterns_subtitle')}
          >
            {isLoading && !quality ? (
              <Skeleton variant="rounded" height={160} />
            ) : !quality?.items.length ? (
              <Typography variant="body2" color="text.secondary">
                {t('analytics.empty_quality_filter')}
              </Typography>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                {qualityRowsOrdered.map((row: QualityPatternRow) => (
                  <Box
                    key={row.issue_type}
                    sx={{
                      p: 1.25,
                      border: 1,
                      borderColor: 'divider',
                      borderRadius: 1.5,
                      bgcolor: qualityPriority(row.issue_type) <= 2 ? 'background.default' : 'transparent',
                    }}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="body2" fontWeight={qualityPriority(row.issue_type) <= 2 ? 600 : 500}>
                        {translateQualityIssueType(row.issue_type, t)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                        {row.count}
                        {row.percentage != null ? ` · ${(row.percentage * 100).toFixed(1)}%` : ''}
                      </Typography>
                    </Box>
                    <Box sx={{ height: 6, bgcolor: 'action.hover', borderRadius: 1, overflow: 'hidden' }}>
                      <Box
                        sx={{
                          height: '100%',
                          width: `${Math.min(100, (row.percentage ?? 0) * 100)}%`,
                          bgcolor: 'secondary.main',
                        }}
                      />
                    </Box>
                    {row.notes ? (
                      <Typography variant="caption" color="text.secondary">
                        {row.notes}
                      </Typography>
                    ) : null}
                  </Box>
                ))}
              </Box>
            )}
          </SectionCard>
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <SectionCard
            title={t('analytics.aisles_attention_title')}
            subtitle={t('analytics.aisles_attention_subtitle')}
          >
            <FilterToolbar
              onReset={() => setAisleMetricsTableSearch('')}
              resetDisabled={!aisleMetricsTableSearch.trim()}
            >
              <TableSearchField
                label={t('table.search_label')}
                placeholder={t('analytics.search_aisle_metrics_placeholder')}
                value={aisleMetricsTableSearch}
                onChange={setAisleMetricsTableSearch}
                data-testid="metrics-aisle-issues-search"
              />
            </FilterToolbar>
            <DataTable<AisleIssueRow>
              rows={aisleRowsPaged}
              rowKey={(r) => `${r.inventory_id}-${r.aisle_id}`}
              columns={aisleColumns}
              loading={isLoading}
              size="small"
              pagination={{
                page: aislePage,
                pageSize: aislePageSize,
                totalItems: aisleRowsSorted.length,
                onPageChange: setAislePage,
                onPageSizeChange: setAislePageSize,
              }}
              emptyState={
                aisleMetricsTableSearch.trim() && !isLoading && aisleRowsSorted.length === 0
                  ? { message: t('table.empty_no_match') }
                  : { message: t('analytics.empty_aisle_metrics') }
              }
            />
          </SectionCard>
        </Box>
      </Box>
    </Box>
  );
}
