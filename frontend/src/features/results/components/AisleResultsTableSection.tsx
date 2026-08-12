import { useMemo } from 'react';
import { Box, Button, Checkbox, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ResultSummary } from '../types';
import type { ResultsFilterKind } from '../selectors';
import {
  FilterToolbar,
  StatusBadge,
  TableSearchField,
  TableSection,
  type DataTableColumn,
} from '../../../components/ui';
import ResultsQuickFilters from './ResultsQuickFilters';
import ResultsFilteredEmptyState from './ResultsFilteredEmptyState';
import { buildResultsTableColumns } from './resultsTableColumns';
import AisleResultsMergeFeedback from './AisleResultsMergeFeedback';
import type { DataTableSortModel } from '../../../components/ui';
import {
  getReviewStatusLabelForDisplay,
  reviewStatusToBadgeSemanticForDisplay,
} from '../utils/evidenceReviewDisplay';
import { deriveResultPriority } from '../utils/resultPriority';
import i18n from '../../../i18n';

function displaySku(r: ResultSummary): string {
  if (r.sku != null && r.sku.trim() !== '') {
    const s = r.sku.trim();
    if (s.toUpperCase() === 'UNKNOWN') return i18n.t('results.sku_unknown');
    return s;
  }
  return i18n.t('common.em_dash');
}

function displayQty(r: ResultSummary): string {
  const value =
    r.resolvedQty != null && !Number.isNaN(r.resolvedQty) ? r.resolvedQty : r.detectedQty;
  if (value != null && !Number.isNaN(value) && value >= 0) {
    return String(value);
  }
  return i18n.t('common.em_dash');
}

function prioritySemantic(tier: number): 'error' | 'warning' | 'review' | 'neutral' {
  if (tier === 1) return 'error';
  if (tier === 2) return 'warning';
  if (tier === 3) return 'review';
  return 'neutral';
}

export interface AisleResultsTableSectionProps {
  countedTotal: number;
  /** Rows in the loaded results dataset for the selected run (not paginated / not filtered). */
  countedResultRows: number;
  mergeFeedback: { severity: 'success' | 'info'; text: string } | null;
  onResetFilters: () => void;
  resetDisabled: boolean;
  skuSearch: string;
  onSkuSearchChange: (value: string) => void;
  tableSort: 'photo' | 'priority';
  onTableSortChange: (value: 'photo' | 'priority') => void;
  filter: ResultsFilterKind;
  onFilterChange: (value: ResultsFilterKind) => void;
  counts: {
    all: number;
    needs_review: number;
    low_confidence: number;
    qty_zero: number;
    invalid_traceability: number;
    missing_evidence: number;
    with_position: number;
    without_position: number;
  };
  sortedForTableLength: number;
  onClearFilterOnly: () => void;
  tableRows: ResultSummary[];
  onOpenReview: (resultId: string) => void;
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  /** Column sort UI; parent applies ordering before pagination. */
  columnSort?: DataTableSortModel;
  selectedIds?: Set<string>;
  onToggleOne?: (id: string) => void;
  onToggleAllPage?: (ids: string[], select: boolean) => void;
  onClearSelection?: () => void;
  onMergeSelected?: () => void;
  mergeSelectedDisabled?: boolean;
  mergeSelectedLoading?: boolean;
}

export default function AisleResultsTableSection({
  countedTotal,
  countedResultRows,
  mergeFeedback,
  onResetFilters,
  resetDisabled,
  skuSearch,
  onSkuSearchChange,
  tableSort,
  onTableSortChange,
  filter,
  onFilterChange,
  counts,
  sortedForTableLength,
  onClearFilterOnly,
  tableRows,
  onOpenReview,
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
  columnSort,
  selectedIds,
  onToggleOne,
  onToggleAllPage,
  onClearSelection,
  onMergeSelected,
  mergeSelectedDisabled,
  mergeSelectedLoading,
}: AisleResultsTableSectionProps) {
  const { t } = useTranslation();
  const selectionEnabled = Boolean(selectedIds && onToggleOne && onToggleAllPage);
  const pageIds = tableRows.map((r) => (r.sourcePositionId?.trim() || r.id));
  const selectedCount = selectedIds?.size ?? 0;
  const allPageSelected =
    selectionEnabled && pageIds.length > 0 && pageIds.every((id) => selectedIds!.has(id));
  const somePageSelected =
    selectionEnabled && pageIds.some((id) => selectedIds!.has(id));

  const columns = useMemo(() => {
    const base = buildResultsTableColumns({
      t,
      dash: t('common.em_dash'),
      onOpenReview,
    });
    if (!selectionEnabled) return base;
    const selectCol: DataTableColumn<ResultSummary> = {
      id: 'select',
      label: (
        <Checkbox
          size="small"
          checked={allPageSelected}
          indeterminate={!allPageSelected && somePageSelected}
          onChange={() => onToggleAllPage!(pageIds, !allPageSelected)}
          inputProps={{ 'aria-label': t('positions.merge_select_all_page') }}
          data-testid="aisle-results-select-all"
          data-datatable-skip-row-click
        />
      ),
      width: 48,
      cell: (r) => {
        const mergeId = r.sourcePositionId?.trim() || r.id;
        return (
          <Checkbox
            size="small"
            checked={selectedIds!.has(mergeId)}
            onChange={() => onToggleOne!(mergeId)}
            inputProps={{ 'aria-label': t('positions.merge_select_row') }}
            data-testid={`aisle-results-select-${mergeId}`}
            data-datatable-skip-row-click
          />
        );
      },
    };
    return [selectCol, ...base];
  }, [
    t,
    onOpenReview,
    selectionEnabled,
    allPageSelected,
    somePageSelected,
    selectedIds,
    onToggleOne,
    onToggleAllPage,
    tableRows,
  ]);

  const activeFilterCount = (filter !== 'all' ? 1 : 0) + (tableSort !== 'photo' ? 1 : 0);

  return (
    <>
      <Box sx={{ mb: 3, mt: 1 }}>
        <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 600 }}>
          {t('positions.counted_total')}
        </Typography>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main' }}>
          {countedTotal}
        </Typography>
        <Typography
          variant="body2"
          component="div"
          sx={{ color: 'text.secondary', mt: 0.75, mb: 2, lineHeight: 1.4 }}
        >
          {t('positions.counted_items', { count: countedResultRows })}
        </Typography>
      </Box>

      <AisleResultsMergeFeedback feedback={mergeFeedback} />

      {selectionEnabled ? (
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          sx={{ mb: 1.5, flexWrap: 'wrap' }}
        >
          {selectedCount > 0 ? (
            <Typography variant="body2" color="text.secondary" data-testid="aisle-results-selected-count">
              {t('positions.merge_selected_count', { count: selectedCount })}
            </Typography>
          ) : null}
          <Button
            size="small"
            variant="contained"
            disabled={mergeSelectedDisabled ?? selectedCount < 2}
            onClick={onMergeSelected}
            data-testid="aisle-results-merge-selected"
          >
            {mergeSelectedLoading
              ? t('common.loading')
              : t('positions.merge_selected_action')}
          </Button>
          {selectedCount > 0 && onClearSelection ? (
            <Button
              size="small"
              variant="text"
              onClick={onClearSelection}
              data-testid="aisle-results-clear-selection"
            >
              {t('positions.merge_clear_selection')}
            </Button>
          ) : null}
        </Stack>
      ) : null}

      <FilterToolbar
        primary={
          <TableSearchField
            label={t('positions.search_label')}
            placeholder={t('positions.filter_sku_placeholder')}
            value={skuSearch}
            onChange={onSkuSearchChange}
            data-testid="aisle-positions-sku-search"
          />
        }
        filters={
          <Stack spacing={2} sx={{ width: '100%', minWidth: 0 }}>
            <Tooltip title={tableSort === 'photo' ? t('positions.order_api') : t('positions.order_client')}>
              <span>
                <ToggleButtonGroup
                  size="small"
                  exclusive
                  fullWidth
                  value={tableSort}
                  onChange={(_, value) => {
                    if (value != null) onTableSortChange(value);
                  }}
                  aria-label={t('common.row_order')}
                >
                  <ToggleButton value="photo">{t('positions.photo_order')}</ToggleButton>
                  <ToggleButton value="priority">{t('positions.review_priority_sort')}</ToggleButton>
                </ToggleButtonGroup>
              </span>
            </Tooltip>
            <ResultsQuickFilters value={filter} onChange={onFilterChange} counts={counts} />
          </Stack>
        }
        onReset={onResetFilters}
        resetDisabled={resetDisabled}
        activeFilterCount={activeFilterCount}
      />

      {sortedForTableLength === 0 ? (
        <ResultsFilteredEmptyState onClearFilter={onClearFilterOnly} />
      ) : (
        <TableSection
          title={t('positions.title_results')}
          testId="aisle-results-table-section"
          table={{
            rows: tableRows,
            rowKey: (r) => r.id,
            columns,
            sort: columnSort,
            onRowClick: (r) => onOpenReview(r.id),
            mobile: {
              mode: 'card',
              title: (r) => displaySku(r),
              status: (r) => {
                const p = deriveResultPriority(r);
                return <StatusBadge label={p.label} semantic={prioritySemantic(p.tier)} variant="outlined" />;
              },
              ariaLabel: (r) => displaySku(r),
              fields: [
                {
                  id: 'position_code',
                  label: t('results.table_column.position_code'),
                  value: (r) => (r.positionCode?.trim() ? r.positionCode : t('common.em_dash')),
                },
                {
                  id: 'quantity',
                  label: t('results.table_column.quantity'),
                  value: displayQty,
                },
                {
                  id: 'review_status',
                  label: t('results.table_column.review_status'),
                  value: (r) => (
                    <StatusBadge
                      label={getReviewStatusLabelForDisplay(r.reviewStatus)}
                      semantic={reviewStatusToBadgeSemanticForDisplay(r.reviewStatus)}
                      variant="outlined"
                    />
                  ),
                  fullWidth: true,
                },
                {
                  id: 'evidence',
                  label: t('results.table_column.evidence'),
                  value: (r) => (
                    <StatusBadge
                      label={r.hasEvidence ? t('results.evidence_present') : t('results.evidence_missing')}
                      semantic={r.hasEvidence ? 'success' : 'warning'}
                      variant="outlined"
                    />
                  ),
                  fullWidth: true,
                },
              ],
            },
            pagination: {
              page,
              pageSize,
              totalItems,
              onPageChange,
              onPageSizeChange,
            },
          }}
        />
      )}
    </>
  );
}
