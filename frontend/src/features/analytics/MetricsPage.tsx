/**
 * Phase 5.1 — dedicated Metrics / Analytics experience (quality, review burden, processing).
 */

import { useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Button,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Skeleton,
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
import { useInventoriesList } from '../../hooks/useInventories';
import { useAislesList } from '../../hooks/useAisles';
import { formatDate } from '../../utils/formatDate';
import { getApiErrorMessage } from '../../utils/apiErrors';
import { ApiError } from '../../api/types';
import { useAnalyticsDashboard } from './hooks';
import type { AnalyticsQueryParams, InventoryPerformanceRow, AisleIssueRow, QualityPatternRow } from './types';
import TrendBars from './components/TrendBars';

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

  const { data: invList } = useInventoriesList({ page: 1, page_size: 500, sort_by: 'name', sort_dir: 'asc' });
  const inventories = invList?.items ?? [];

  const aislesQuery = useAislesList(inventoryId || undefined, { enabled: Boolean(inventoryId) });
  const aisles = aislesQuery.data?.items ?? [];

  const { summary, trends, inventoryPerformance, aisleIssues, quality, isLoading, isError, errors, refetchAll } =
    useAnalyticsDashboard(params);

  const errMsg =
    isError && errors[0]
      ? errors[0] instanceof ApiError
        ? getApiErrorMessage(errors[0], 'Failed to load metrics')
        : String(errors[0])
      : null;

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
      },
      { id: 'aisles', label: 'Aisles', align: 'right', cell: (r) => r.total_aisles },
      { id: 'positions', label: 'Positions', align: 'right', cell: (r) => r.total_positions },
      { id: 'processed', label: 'Processed', align: 'right', cell: (r) => r.processed_positions },
      { id: 'review_rate', label: 'Review rate', align: 'right', cell: (r) => formatPct(r.review_rate) },
      { id: 'correction_rate', label: 'Correction rate', align: 'right', cell: (r) => formatPct(r.correction_rate) },
      {
        id: 'invalid_tr',
        label: 'Invalid trace.',
        align: 'right',
        cell: (r) => formatPct(r.invalid_traceability_rate),
      },
      {
        id: 'avg_conf',
        label: 'Avg conf.',
        align: 'right',
        cell: (r) => (r.avg_confidence != null ? `${(r.avg_confidence * 100).toFixed(0)}%` : '—'),
      },
      {
        id: 'proc',
        label: 'Job success',
        align: 'right',
        cell: (r) => formatPct(r.processing_success_rate),
      },
    ],
    []
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
      { id: 'total', label: 'Results', align: 'right', cell: (r) => r.total_results },
      { id: 'pending', label: 'Pending review', align: 'right', cell: (r) => r.needs_review_count },
      { id: 'corrected', label: 'Corrected', align: 'right', cell: (r) => r.corrected_count },
      { id: 'inv_tr', label: 'Invalid tr.', align: 'right', cell: (r) => r.invalid_traceability_count },
      { id: 'low_c', label: 'Low conf.', align: 'right', cell: (r) => r.low_confidence_count },
      { id: 'issue', label: 'Top issue', cell: (r) => r.most_common_issue ?? '—' },
    ],
    []
  );

  const kpiCards = [
    {
      label: 'Auto acceptance rate',
      value: formatPct(summary?.auto_acceptance_rate),
      description: 'Confirm / settling actions',
    },
    {
      label: 'Manual correction rate',
      value: formatPct(summary?.manual_correction_rate),
      description: 'SKU/Qty corrections / settling',
    },
    {
      label: 'Invalid traceability rate',
      value: formatPct(summary?.invalid_traceability_rate),
      description: 'Invalid / active positions',
    },
    {
      label: 'Processing success rate',
      value: formatPct(summary?.processing_success_rate),
      description: 'Succeeded / (succeeded+failed) jobs',
    },
    {
      label: 'Average review time',
      value: formatAvgReviewSec(summary?.average_review_time_seconds),
      description: 'First settling action minus position created',
    },
    {
      label: 'Reviewed results / day',
      value: summary?.reviewed_results_per_day != null ? summary.reviewed_results_per_day.toFixed(1) : '—',
      description: `Settling actions / day span (${summary?.period_day_count ?? 1})`,
    },
  ];

  return (
    <Box sx={{ pb: 4 }}>
      {errMsg ? <ErrorAlert message={errMsg} onRetry={() => refetchAll()} /> : null}

      <Typography variant="h5" component="h1" fontWeight={700} gutterBottom>
        Metrics & analytics
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 720 }}>
        Quality, review burden, traceability health, and processing performance. Filters scope all sections below.
      </Typography>

      <FilterToolbar
        onReset={() => {
          const d = defaultDateRange();
          setDateFrom(d.from);
          setDateTo(d.to);
          setInventoryId('');
          setAisleId('');
        }}
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
            <MenuItem value="">All inventories</MenuItem>
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
        <Button size="small" variant="outlined" onClick={() => refetchAll()} disabled={isLoading}>
          Refresh
        </Button>
      </FilterToolbar>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        {isLoading && !summary
          ? Array.from({ length: 6 }).map((_, i) => (
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
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
          {summary.notes.join(' ')}
        </Typography>
      ) : null}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <SectionCard title="Review activity" subtitle="Settling review actions per day">
            <TrendBars
              title=""
              points={trends?.reviewed_results_over_time ?? []}
              emptyMessage="No review actions in this range."
            />
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <SectionCard title="Processing outcomes" subtitle="Terminal jobs per day (bar height = job count)">
            <TrendBars
              title=""
              points={trends?.processing_success_over_time ?? []}
              emptyMessage="No completed/failed jobs in this range."
            />
          </SectionCard>
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <SectionCard
            title="Quality patterns"
            subtitle="Distribution of primary issue buckets (non–mutually exclusive priority order in backend)"
          >
            {isLoading && !quality ? (
              <Skeleton variant="rounded" height={160} />
            ) : !quality?.items.length ? (
              <Typography variant="body2" color="text.secondary">
                No positions in scope for this filter.
              </Typography>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                {quality.items.map((row: QualityPatternRow) => (
                  <Box key={row.issue_type}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="body2">{row.issue_type}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {row.count}
                        {row.percentage != null ? ` (${(row.percentage * 100).toFixed(0)}%)` : ''}
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
          <SectionCard title="Aisles with review pressure" subtitle="Sorted by pending review count">
            <DataTable<AisleIssueRow>
              rows={aisleIssues?.items ?? []}
              rowKey={(r) => `${r.inventory_id}-${r.aisle_id}`}
              columns={aisleColumns}
              loading={isLoading}
              size="small"
              emptyState={{ message: 'No aisle-level data for this filter.' }}
            />
          </SectionCard>
        </Grid>
      </Grid>

      <SectionCard title="Inventory performance" subtitle="Coverage, review intensity, and job outcomes by inventory">
        <DataTable<InventoryPerformanceRow>
          rows={inventoryPerformance?.items ?? []}
          rowKey={(r) => r.inventory_id}
          columns={invColumns}
          loading={isLoading}
          emptyState={{ message: 'No inventory performance rows for this filter.' }}
        />
      </SectionCard>
    </Box>
  );
}
