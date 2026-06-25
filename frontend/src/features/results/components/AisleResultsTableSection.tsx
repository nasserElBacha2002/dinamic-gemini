import { useMemo } from 'react';
import { Box, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ResultSummary } from '../types';
import type { ResultsFilterKind } from '../selectors';
import { FilterToolbar, TableSearchField, TableSection } from '../../../components/ui';
import ResultsQuickFilters from './ResultsQuickFilters';
import ResultsFilteredEmptyState from './ResultsFilteredEmptyState';
import { buildResultsTableColumns } from './resultsTableColumns';
import AisleResultsMergeFeedback from './AisleResultsMergeFeedback';
import type { DataTableSortModel } from '../../../components/ui';

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
}: AisleResultsTableSectionProps) {
  const { t } = useTranslation();

  const columns = useMemo(
    () =>
      buildResultsTableColumns({
        t,
        dash: t('common.em_dash'),
        onOpenReview,
      }),
    [t, onOpenReview]
  );

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

      <FilterToolbar onReset={onResetFilters} resetDisabled={resetDisabled}>
        <TableSearchField
          label={t('positions.search_label')}
          placeholder={t('positions.filter_sku_placeholder')}
          value={skuSearch}
          onChange={onSkuSearchChange}
          data-testid="aisle-positions-sku-search"
        />
        <Tooltip title={tableSort === 'photo' ? t('positions.order_api') : t('positions.order_client')}>
          <span>
            <ToggleButtonGroup
              size="small"
              exclusive
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
      </FilterToolbar>

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
