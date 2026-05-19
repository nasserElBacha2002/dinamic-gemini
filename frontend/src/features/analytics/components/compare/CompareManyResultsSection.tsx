import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { buildDifferenceSummary } from '../../compare/compareBenchmarkViewModel';
import CompareDifferenceSummary from '../../compare/components/CompareDifferenceSummary';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Alert, Box, Button, Paper, Typography } from '@mui/material';
import {
  DataTable,
  sortDataTableRows,
  type DataTableColumn,
  type DataTableSortDirection,
} from '../../../../components/ui';
import { semanticColor, signedValue } from '../../adapters/compareFormatters';

type CompareManyDiffRow = {
  match_key: string;
  side: string;
  quantity_a?: number | null;
  quantity_b?: number | null;
  sku_a?: string | null;
  sku_b?: string | null;
  position_code_a?: string | null;
  position_code_b?: string | null;
};

type CompareManyComparison = {
  baseline_job_id: string;
  target_job_id: string;
  diff_summary: {
    keys_only_in_a: number;
    keys_only_in_b: number;
    keys_in_both: number;
    quantity_changed: number;
    sku_changed: number;
    position_code_changed: number;
  };
  delta: {
    needs_review_diff: number;
    unknown_internal_code_diff: number;
    total_quantity_diff: number;
    consolidated_positions_diff: number;
    execution_time_delta?: number | null;
  };
  diff_rows: CompareManyDiffRow[];
  diff_rows_truncated: boolean;
};

type CompareManyResultsSectionProps = {
  orderedComparisons: CompareManyComparison[];
  expandedTargetJobId: string | null;
  isEnrichedFetching: boolean;
  hasEnrichedData: boolean;
  targetStatusByJobId: Map<string, string | undefined>;
  onToggleExpanded: (targetJobId: string, expanded: boolean) => void;
  insightText: (comp: CompareManyComparison) => string | null;
  deltaExecutionLabel: (value: number) => string;
  baselineVsTargetLabel: (baseline: string, target: string) => string;
  /** When set, titles each comparison block using full job ids (e.g. model labels from loaded runs). */
  comparisonTitleForJobIds?: (baselineJobId: string, targetJobId: string) => string;
  diffSummaryLabel: (values: {
    onlyBaseline: number;
    onlyTarget: number;
    both: number;
    qty: number;
    sku: number;
    pos: number;
  }) => string;
  labels: {
    hide: string;
    showDiffRows: string;
    targetNonIdealStatus: string;
    deltaNeedsReview: (value: string) => string;
    deltaUnknown: (value: string) => string;
    deltaTotalQty: (value: string) => string;
    deltaConsolidated: (value: string) => string;
    deltaExecutionTime: (value: string) => string;
    noDifferences: string;
    loadingDiffRows: string;
    noDiffRows: string;
    colKey: string;
    colSide: string;
    colQtyA: string;
    colQtyB: string;
    colSkuA: string;
    colSkuB: string;
    colPosA: string;
    colPosB: string;
    emDash: string;
  };
};

function CompareManyDiffTable({
  rows,
  labels,
}: {
  rows: CompareManyDiffRow[];
  labels: CompareManyResultsSectionProps['labels'];
}) {
  const [sortBy, setSortBy] = useState('');
  const [sortDir, setSortDir] = useState<DataTableSortDirection>('asc');
  const em = labels.emDash;

  const columns = useMemo<DataTableColumn<CompareManyDiffRow>[]>(
    () => [
      {
        id: 'match_key',
        label: labels.colKey,
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => r.match_key.toLowerCase(),
        cell: (r) => (
          <Typography component="span" variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
            {r.match_key}
          </Typography>
        ),
      },
      {
        id: 'side',
        label: labels.colSide,
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => r.side.toLowerCase(),
        cell: (r) => r.side,
      },
      {
        id: 'quantity_a',
        label: labels.colQtyA,
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (r) => r.quantity_a,
        cell: (r) => r.quantity_a ?? em,
      },
      {
        id: 'quantity_b',
        label: labels.colQtyB,
        align: 'right',
        sortable: true,
        sortType: 'number',
        sortAccessor: (r) => r.quantity_b,
        cell: (r) => r.quantity_b ?? em,
      },
      {
        id: 'sku_a',
        label: labels.colSkuA,
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => (r.sku_a ?? '').toLowerCase(),
        cell: (r) => r.sku_a ?? em,
      },
      {
        id: 'sku_b',
        label: labels.colSkuB,
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => (r.sku_b ?? '').toLowerCase(),
        cell: (r) => r.sku_b ?? em,
      },
      {
        id: 'position_code_a',
        label: labels.colPosA,
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => (r.position_code_a ?? '').toLowerCase(),
        cell: (r) => r.position_code_a ?? em,
      },
      {
        id: 'position_code_b',
        label: labels.colPosB,
        sortable: true,
        sortType: 'string',
        sortAccessor: (r) => (r.position_code_b ?? '').toLowerCase(),
        cell: (r) => r.position_code_b ?? em,
      },
    ],
    [em, labels]
  );

  const displayRows = useMemo(
    () => (!sortBy.trim() ? [...rows] : sortDataTableRows(rows, columns, sortBy, sortDir)),
    [rows, columns, sortBy, sortDir]
  );

  return (
    <DataTable<CompareManyDiffRow>
      rows={displayRows}
      rowKey={(r) => `${r.match_key}-${r.side}`}
      columns={columns}
      size="small"
      rowHover={false}
      sort={{
        sortBy,
        sortDir,
        onSortChange: (sb: string, sd: DataTableSortDirection) => {
          setSortBy(sb);
          setSortDir(sd);
        },
      }}
    />
  );
}

export default function CompareManyResultsSection({
  orderedComparisons,
  expandedTargetJobId,
  isEnrichedFetching,
  hasEnrichedData,
  targetStatusByJobId,
  onToggleExpanded,
  insightText,
  deltaExecutionLabel,
  baselineVsTargetLabel,
  comparisonTitleForJobIds,
  diffSummaryLabel,
  labels,
}: CompareManyResultsSectionProps) {
  const { t } = useTranslation();

  return (
    <>
      {orderedComparisons.map((comp) => {
        const expanded = expandedTargetJobId === comp.target_job_id;
        const diffRowsLoading = expanded && isEnrichedFetching && !hasEnrichedData;
        const hasDiffRowsLoaded = expanded && hasEnrichedData && !diffRowsLoading;
        const differenceSummary = buildDifferenceSummary(comp, hasDiffRowsLoaded, t);
        const noDifferences =
          comp.diff_summary.keys_only_in_a === 0 &&
          comp.diff_summary.keys_only_in_b === 0 &&
          comp.diff_summary.quantity_changed === 0 &&
          comp.diff_summary.sku_changed === 0 &&
          comp.diff_summary.position_code_changed === 0;
        const insightLine = insightText(comp);
        return (
          <Paper variant="outlined" sx={{ p: 2 }} key={comp.target_job_id} data-testid="compare-many-comparison-block">
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography variant="subtitle1">
                {comparisonTitleForJobIds
                  ? comparisonTitleForJobIds(comp.baseline_job_id, comp.target_job_id)
                  : baselineVsTargetLabel(comp.baseline_job_id.slice(0, 8), comp.target_job_id.slice(0, 8))}
              </Typography>
              <Button
                size="small"
                onClick={() => onToggleExpanded(comp.target_job_id, expanded)}
                endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              >
                {expanded ? labels.hide : labels.showDiffRows}
              </Button>
            </Box>
            {targetStatusByJobId.get(comp.target_job_id) !== 'succeeded' ? (
              <Alert severity="warning" sx={{ mb: 1 }}>
                {labels.targetNonIdealStatus}
              </Alert>
            ) : null}

            <CompareDifferenceSummary model={differenceSummary} />

            <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
              <Typography sx={{ color: semanticColor(comp.delta.needs_review_diff, true) }}>
                {labels.deltaNeedsReview(signedValue(comp.delta.needs_review_diff))}
              </Typography>
              <Typography sx={{ color: semanticColor(comp.delta.unknown_internal_code_diff, true) }}>
                {labels.deltaUnknown(signedValue(comp.delta.unknown_internal_code_diff))}
              </Typography>
              <Typography>{labels.deltaTotalQty(signedValue(comp.delta.total_quantity_diff))}</Typography>
              <Typography>{labels.deltaConsolidated(signedValue(comp.delta.consolidated_positions_diff))}</Typography>
              {comp.delta.execution_time_delta != null ? (
                <Typography sx={{ color: semanticColor(comp.delta.execution_time_delta, true) }}>
                  {labels.deltaExecutionTime(deltaExecutionLabel(comp.delta.execution_time_delta))}
                </Typography>
              ) : null}
            </Box>

            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              {diffSummaryLabel({
                onlyBaseline: comp.diff_summary.keys_only_in_a,
                onlyTarget: comp.diff_summary.keys_only_in_b,
                both: comp.diff_summary.keys_in_both,
                qty: comp.diff_summary.quantity_changed,
                sku: comp.diff_summary.sku_changed,
                pos: comp.diff_summary.position_code_changed,
              })}
            </Typography>
            {insightLine ? (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                {insightLine}
              </Typography>
            ) : null}

            {noDifferences ? (
              <Alert severity="success" sx={{ mt: 1 }}>
                {labels.noDifferences}
              </Alert>
            ) : null}

            {expanded ? (
              <Box sx={{ mt: 2 }} data-testid="compare-many-diff-rows-panel">
                {diffRowsLoading ? <Typography>{labels.loadingDiffRows}</Typography> : null}
                {!diffRowsLoading ? (
                  <Box sx={{ overflowX: 'auto' }}>
                    <CompareManyDiffTable rows={comp.diff_rows} labels={labels} />
                  </Box>
                ) : null}
                {!diffRowsLoading && comp.diff_rows.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {labels.noDiffRows}
                  </Typography>
                ) : null}
              </Box>
            ) : null}
          </Paper>
        );
      })}
    </>
  );
}
