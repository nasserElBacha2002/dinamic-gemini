/**
 * Operational analytics dashboard focused on efficiency, manual effort, and quality hotspots.
 */

import { useEffect, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Alert,
  Chip,
  Box,
  Button,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  DataTable,
  ErrorAlert,
  FilterToolbar,
  KpiCard,
  SectionCard,
  type DataTableColumn,
} from '../../components/ui';
import { PageHeader } from '../../components/shell';
import { useInventoriesList } from '../../hooks/useInventories';
import { useAislesList } from '../../hooks/useAisles';
import { formatDate } from '../../utils/formatDate';
import { getApiErrorMessage } from '../../utils/apiErrors';
import { ApiError } from '../../api/types';
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
  if (x == null || Number.isNaN(x)) return '—';
  return `${(x * 100).toFixed(1)}%`;
}

function formatAvgReviewSec(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  return `${(sec / 60).toFixed(1)} min`;
}

function formatAvgReviewMinutes(minutes: number | null | undefined, seconds: number | null | undefined): string {
  if (minutes != null && !Number.isNaN(minutes)) return `${minutes.toFixed(1)} min`;
  return formatAvgReviewSec(seconds);
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
      case 'unknown':
        return row.unknown_rate ?? null;
      case 'invalid_tr':
        return row.invalid_traceability_rate;
      case 'avg_conf':
        return row.avg_confidence;
      case 'avg_review':
        return row.average_review_time_minutes ?? null;
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
  if (normalized === 'unknown') return 0;
  if (normalized === 'pending review') return 1;
  if (normalized === 'invalid traceability') return 2;
  if (normalized === 'missing evidence') return 3;
  if (normalized.includes('zero')) return 4;
  if (normalized === 'low confidence') return 5;
  if (normalized === 'no primary issue') return 6;
  return 50;
}

function interventionLabel(category: string): string {
  switch (category) {
    case 'confirmed':
      return 'Confirmed';
    case 'qty_corrected':
      return 'Qty corrected';
    case 'sku_corrected':
      return 'SKU corrected';
    case 'invalid':
      return 'Invalid';
    case 'unknown':
      return 'Unknown';
    case 'deleted':
      return 'Deleted';
    default:
      return category;
  }
}

function interventionPriority(category: string): number {
  switch (category) {
    case 'unknown':
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
    case 'unknown':
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

export default function MetricsPage() {
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

  useEffect(() => {
    if (aisleId && !aisles.some((aisle) => aisle.id === aisleId)) {
      setAisleId('');
    }
  }, [aisleId, aisles]);

  const [inventoryPage, setInventoryPage] = useState(1);
  const [inventoryPageSize, setInventoryPageSize] = useState(10);
  const [inventorySortBy, setInventorySortBy] = useState('auto_accept');
  const [inventorySortDir, setInventorySortDir] = useState<'asc' | 'desc'>('desc');
  const [aislePage, setAislePage] = useState(1);
  const [aislePageSize, setAislePageSize] = useState(10);

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
        ? getApiErrorMessage(errors[0], 'Failed to load metrics')
        : String(errors[0])
      : null;

  const inventoryRowsSorted = useMemo(
    () => sortInventoryRows(inventoryPerformance?.items ?? [], inventorySortBy, inventorySortDir),
    [inventoryPerformance?.items, inventorySortBy, inventorySortDir]
  );
  const inventoryRowsPaged = useMemo(
    () => paginateRows(inventoryRowsSorted, inventoryPage, inventoryPageSize),
    [inventoryRowsSorted, inventoryPage, inventoryPageSize]
  );
  const aisleRowsSorted = useMemo(
    () =>
      [...(aisleIssues?.items ?? [])].sort(
        (left, right) =>
          (numberOrZero(right.needs_review_count) +
            numberOrZero(right.unknown_count) +
            numberOrZero(right.manual_corrections_count ?? right.corrected_count) +
            numberOrZero(right.invalid_traceability_count)) -
            (numberOrZero(left.needs_review_count) +
              numberOrZero(left.unknown_count) +
              numberOrZero(left.manual_corrections_count ?? left.corrected_count) +
              numberOrZero(left.invalid_traceability_count)) ||
          numberOrZero(right.needs_review_count) - numberOrZero(left.needs_review_count) ||
          numberOrZero(right.total_results) - numberOrZero(left.total_results)
      ),
    [aisleIssues?.items]
  );
  const aisleRowsPaged = useMemo(
    () => paginateRows(aisleRowsSorted, aislePage, aislePageSize),
    [aisleRowsSorted, aislePage, aislePageSize]
  );
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
  const hasUnknownRate = summary?.unknown_rate != null;
  const unknownPositionsCount = summary?.unknown_count ?? 0;
  const totalPositionsCount = summary?.total_positions_in_scope ?? summary?.positions_in_scope ?? 0;
  const processedPositionsCount = summary?.processed_positions_count ?? 0;
  const reviewedPositionsCount = summary?.reviewed_positions_count ?? 0;
  const interventionPositionsCount = manualInterventions?.intervention_positions_count ?? 0;
  const resolutionFlowStages = [
    {
      label: 'Positions in scope',
      value: totalPositionsCount,
      helper: 'Total current scope after inventory and aisle filters',
    },
    {
      label: 'Pending review',
      value: pendingReviewCount,
      helper: 'Positions still requiring operator attention',
    },
    {
      label: 'Processed',
      value: processedPositionsCount,
      helper: 'Operationally processed positions in scope',
    },
    {
      label: 'Reviewed',
      value: reviewedPositionsCount,
      helper: 'Positions with a terminal review action',
    },
    {
      label: 'Manual touch',
      value: interventionPositionsCount,
      helper: 'Positions touched by an operator action',
    },
    ...(hasUnknownRate
      ? [
          {
            label: 'Unknown',
            value: unknownPositionsCount,
            helper: 'Explicit terminal unknown resolutions only',
          },
        ]
      : []),
  ];

  const invColumns = useMemo<DataTableColumn<InventoryPerformanceRow>[]>(
    () => [
      {
        id: 'name',
        label: 'Inventory',
        sortable: false,
        cell: (r) => (
          <Typography
            component={RouterLink}
            to={`/inventories/${r.inventory_id}`}
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
        label: 'Created',
        cell: (r) => formatDate(r.inventory_created_at),
        sortable: true,
      },
      { id: 'aisles', label: 'Aisles', align: 'right', sortable: true, cell: (r) => r.aisles_count ?? r.total_aisles },
      { id: 'positions', label: 'Positions', align: 'right', sortable: true, cell: (r) => r.positions_count ?? r.total_positions },
      { id: 'processed', label: 'Processed', align: 'right', sortable: true, cell: (r) => r.processed_count ?? r.processed_positions },
      {
        id: 'auto_accept',
        label: 'Auto-accept rate',
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.auto_acceptance_rate),
      },
      {
        id: 'manual_correction',
        label: 'Manual correction rate',
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.manual_correction_rate ?? r.correction_rate),
      },
      ...(hasUnknownRate
        ? [
            {
              id: 'unknown',
              label: 'Unknown rate',
              align: 'right' as const,
              sortable: true,
              cell: (r: InventoryPerformanceRow) => formatPct(r.unknown_rate),
            },
          ]
        : []),
      {
        id: 'invalid_tr',
        label: 'Invalid traceability',
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.invalid_traceability_rate),
      },
      {
        id: 'avg_conf',
        label: 'Avg confidence',
        align: 'right',
        sortable: true,
        cell: (r) => (r.avg_confidence != null ? `${(r.avg_confidence * 100).toFixed(0)}%` : '—'),
      },
      {
        id: 'avg_review',
        label: 'Avg review time',
        align: 'right',
        sortable: true,
        cell: (r) => formatAvgReviewMinutes(r.average_review_time_minutes, null),
      },
      {
        id: 'proc',
        label: 'Job success rate',
        align: 'right',
        sortable: true,
        cell: (r) => formatPct(r.processing_success_rate),
      },
    ],
    [hasUnknownRate]
  );

  const aisleColumns = useMemo<DataTableColumn<AisleIssueRow>[]>(
    () => [
      {
        id: 'aisle',
        label: 'Aisle',
        cell: (r) => (
          <Typography
            component={RouterLink}
            to={`/inventories/${r.inventory_id}/aisles/${r.aisle_id}/positions`}
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
        label: 'Inventory',
        cell: (r) => (
          <Typography variant="body2" color="text.secondary">
            {r.inventory_name}
          </Typography>
        ),
      },
      { id: 'total', label: 'Positions', align: 'right', cell: (r) => r.total_results },
      { id: 'pending', label: 'Pending review', align: 'right', cell: (r) => r.needs_review_count },
      { id: 'unknown', label: 'Unknown', align: 'right', cell: (r) => r.unknown_count ?? 0 },
      { id: 'inv_tr', label: 'Invalid traceability', align: 'right', cell: (r) => r.invalid_traceability_count },
      {
        id: 'manual_c',
        label: 'Manual corrections',
        align: 'right',
        cell: (r) => r.manual_corrections_count ?? r.corrected_count,
      },
    ],
    []
  );

  const kpiCards = [
    {
      label: 'Auto-acceptance rate',
      value: formatPct(summary?.auto_acceptance_rate),
      description: summary?.reviewed_positions_count
        ? `${Math.round((summary.auto_acceptance_rate ?? 0) * summary.reviewed_positions_count)} of ${summary.reviewed_positions_count} reviewed positions`
        : 'Reviewed positions resolved without manual correction',
    },
    {
      label: 'Manual correction rate',
      value: formatPct(summary?.manual_correction_rate),
      description: summary?.reviewed_positions_count
        ? `${Math.round((summary.manual_correction_rate ?? 0) * summary.reviewed_positions_count)} of ${summary.reviewed_positions_count} reviewed positions`
        : 'SKU or quantity corrections among reviewed positions',
    },
    ...(hasUnknownRate
      ? [
          {
            label: 'Unknown rate',
            value: formatPct(summary?.unknown_rate),
            description:
              summary?.unknown_count != null && summary?.reviewed_positions_count
                ? `${summary.unknown_count} of ${summary.reviewed_positions_count} reviewed positions`
                : 'Final unknown resolutions in scope',
          },
        ]
      : []),
    {
      label: 'Processing success rate',
      value: formatPct(summary?.processing_success_rate),
      description: 'Succeeded aisle jobs among terminal jobs in the selected period',
    },
    {
      label: 'Average review time',
      value: formatAvgReviewMinutes(summary?.average_review_time_minutes, summary?.average_review_time_seconds),
      description: 'From result creation to the first settling review action',
    },
    {
      label: 'Invalid traceability rate',
      value: formatPct(summary?.invalid_traceability_rate),
      description: summary?.total_positions_in_scope
        ? `${Math.round((summary.invalid_traceability_rate ?? 0) * summary.total_positions_in_scope)} of ${summary.total_positions_in_scope} positions in scope`
        : 'Positions with invalid traceability in scope',
    },
  ];

  const scopeSummary = summary
    ? {
        inventoryLabel: selectedInventory ? selectedInventory.name : 'All inventories in scope',
        aisleLabel: selectedAisle
          ? selectedAisle.code
          : inventoryId
            ? 'All aisles in the selected inventory'
            : 'All aisles in scope',
        positions: summary.total_positions_in_scope ?? summary.positions_in_scope,
      }
    : null;

  return (
    <Box sx={{ pb: 4 }}>
      {errMsg ? <ErrorAlert message={errMsg} onRetry={() => refetchAll()} /> : null}

      <PageHeader a11yTitle="Metrics" />

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
          <Button size="small" variant="outlined" onClick={() => refetchAll()} disabled={isLoading}>
            Refresh
          </Button>
        }
      >
        <TextField
          size="small"
          label="From"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 150 }}
        />
        <TextField
          size="small"
          label="To"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ minWidth: 150 }}
        />
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="metrics-inv-label">Inventory</InputLabel>
          <Select
            labelId="metrics-inv-label"
            label="Inventory"
            value={inventoryId}
            onChange={(e) => {
              setInventoryId(e.target.value);
              setAisleId('');
            }}
          >
            <MenuItem value="">All inventories in scope</MenuItem>
            {inventories.map((inv) => (
              <MenuItem key={inv.id} value={inv.id}>
                {inv.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 180 }} disabled={!inventoryId}>
          <InputLabel id="metrics-aisle-label">Aisle</InputLabel>
          <Select
            labelId="metrics-aisle-label"
            label="Aisle"
            value={aisleId}
            onChange={(e) => setAisleId(e.target.value)}
          >
            <MenuItem value="">All aisles</MenuItem>
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
          Failed to load inventory filter options. Global scope is still available.
        </Alert>
      ) : null}

      {scopeSummary ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Inventory scope: {scopeSummary.inventoryLabel}
          {' · '}
          Aisle scope: {scopeSummary.aisleLabel}
          {' · '}
          Positions in scope: {scopeSummary.positions}
        </Typography>
      ) : null}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        {isLoading && !summary
          ? Array.from({ length: hasUnknownRate ? 6 : 5 }).map((_, i) => (
              <Grid item xs={12} sm={6} md={4} key={`sk-${i}`}>
                <Skeleton variant="rounded" height={100} />
              </Grid>
            ))
          : kpiCards.map((k) => (
              <Grid item xs={12} sm={6} md={4} key={k.label}>
                <KpiCard label={k.label} value={k.value} description={k.description} />
              </Grid>
            ))}
      </Grid>

      {summary?.notes?.length ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {summary.notes.join(' ')}
        </Alert>
      ) : null}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <SectionCard
            title="Manual intervention breakdown"
            subtitle="Persisted operator outcomes, with counts and percentages against reviewed positions."
          >
            {isLoading && !manualInterventions ? (
              <Skeleton variant="rounded" height={220} />
            ) : supportedInterventions.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No persisted manual interventions match this scope.
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
                    Reviewed positions
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {manualInterventions?.reviewed_positions_count ?? 0}
                  </Typography>
                </Box>
                {orderedSupportedInterventions.map((item: ManualInterventionCategory) => (
                  <Box key={item.category}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, mb: 0.5 }}>
                      <Typography variant="body2" fontWeight={600}>
                        {interventionLabel(item.category)}
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
                      Awaiting explicit backend/domain support:
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {unsupportedInterventions.map((item: ManualInterventionCategory) => (
                        <Chip
                          key={item.category}
                          label={`${interventionLabel(item.category)} unavailable`}
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
        </Grid>
        <Grid item xs={12} md={6}>
          <SectionCard
            title="Resolution flow"
            subtitle="Truthful scope progression using current processed, reviewed, and operator-action counts."
          >
            {isLoading && !summary ? (
              <Skeleton variant="rounded" height={220} />
            ) : (
              <Stack spacing={1.25}>
                <Grid container spacing={1.5}>
                  {resolutionFlowStages.map((item) => (
                    <Grid item xs={6} md={hasUnknownRate ? 4 : 3} key={item.label}>
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
                    </Grid>
                  ))}
                </Grid>
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
                        {index < resolutionFlowStages.length - 1 ? 'Step' : 'Outcome'}
                      </Typography>
                      <Box sx={{ height: 10, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
                        <Box
                          sx={{
                            height: '100%',
                            width: `${totalPositionsCount > 0 ? Math.min(100, (item.value / totalPositionsCount) * 100) : 0}%`,
                            bgcolor: index === resolutionFlowStages.length - 1 && hasUnknownRate ? 'warning.main' : 'primary.main',
                          }}
                        />
                      </Box>
                    </Box>
                  ))}
                </Box>
                <Typography variant="caption" color="text.secondary">
                  Manual corrections in scope: {manualCorrectionCount}
                  {hasUnknownRate ? ` · Unknown outcomes: ${unknownPositionsCount}` : ''}
                </Typography>
              </Stack>
            )}
          </SectionCard>
        </Grid>
      </Grid>

      <SectionCard
        title="Inventory performance"
        subtitle="Primary comparison table for efficiency, review burden, and quality by inventory."
      >
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
          emptyState={{ message: 'No inventory performance data for this filter.' }}
        />
      </SectionCard>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <SectionCard
            title="Quality patterns"
            subtitle="Mutually exclusive issue buckets ordered by operational attention priority."
          >
            {isLoading && !quality ? (
              <Skeleton variant="rounded" height={160} />
            ) : !quality?.items.length ? (
              <Typography variant="body2" color="text.secondary">
                No positions match this filter and date range.
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
                        {row.issue_type}
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
        </Grid>
        <Grid item xs={12} md={6}>
          <SectionCard
            title="Aisles requiring attention"
            subtitle="Compact secondary table for aisles with the highest current review and quality pressure."
          >
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
              emptyState={{ message: 'No aisle-level metrics for this filter.' }}
            />
          </SectionCard>
        </Grid>
      </Grid>
    </Box>
  );
}
