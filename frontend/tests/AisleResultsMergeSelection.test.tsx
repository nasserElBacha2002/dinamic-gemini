import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import type { ComponentProps, ReactElement } from 'react';
import i18n from '../src/i18n';
import AisleResultsTableSection from '../src/features/results/components/AisleResultsTableSection';
import type { ResultSummary } from '../src/features/results/types';

function wrap(ui: ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

function row(partial: Partial<ResultSummary> & Pick<ResultSummary, 'id'>): ResultSummary {
  return {
    sku: 'SKU-1',
    positionCode: 'A01',
    detectedQty: 1,
    correctedQty: null,
    resolvedQty: 1,
    confidence: 0.9,
    reviewStatus: 'NEEDS_REVIEW',
    traceabilityStatus: 'VALID',
    needsReview: true,
    updatedAt: '2026-08-12T12:00:00Z',
    hasEvidence: true,
    hasValidEvidence: true,
    sourcePositionId: partial.sourcePositionId ?? partial.id,
    ...partial,
  };
}

describe('AisleResultsTableSection merge selection', () => {
  const baseCounts = {
    all: 2,
    needs_review: 2,
    low_confidence: 0,
    qty_zero: 0,
    invalid_traceability: 0,
    missing_evidence: 0,
    with_position: 0,
    without_position: 2,
  };

  function renderSection(
    props: Partial<ComponentProps<typeof AisleResultsTableSection>> & {
      tableRows: ResultSummary[];
      selectedIds: Set<string>;
    }
  ) {
    const {
      tableRows,
      selectedIds,
      onToggleOne = () => undefined,
      onToggleAllPage = () => undefined,
      onClearSelection = () => undefined,
      onMergeSelected = () => undefined,
      mergeSelectedDisabled = selectedIds.size < 2,
      ...rest
    } = props;
    return wrap(
      <AisleResultsTableSection
        countedTotal={tableRows.length}
        countedResultRows={tableRows.length}
        mergeFeedback={null}
        onResetFilters={() => undefined}
        resetDisabled
        skuSearch=""
        onSkuSearchChange={() => undefined}
        tableSort="photo"
        onTableSortChange={() => undefined}
        filter="all"
        onFilterChange={() => undefined}
        counts={baseCounts}
        sortedForTableLength={tableRows.length}
        onClearFilterOnly={() => undefined}
        tableRows={tableRows}
        onOpenReview={() => undefined}
        page={1}
        pageSize={25}
        totalItems={tableRows.length}
        onPageChange={() => undefined}
        onPageSizeChange={() => undefined}
        selectedIds={selectedIds}
        onToggleOne={onToggleOne}
        onToggleAllPage={onToggleAllPage}
        onClearSelection={onClearSelection}
        onMergeSelected={onMergeSelected}
        mergeSelectedDisabled={mergeSelectedDisabled}
        {...rest}
      />
    );
  }

  it('selects by sourcePositionId and enables merge at 2+', () => {
    const selected = new Set<string>();
    const onToggleOne = vi.fn((id: string) => {
      if (selected.has(id)) selected.delete(id);
      else selected.add(id);
    });
    const onMergeSelected = vi.fn();
    const rows = [
      row({ id: 'prod-a', sourcePositionId: 'pos-1', sku: 'SKU-1' }),
      row({ id: 'prod-b', sourcePositionId: 'pos-2', sku: 'SKU-1' }),
    ];

    const { rerender } = renderSection({
      tableRows: rows,
      selectedIds: selected,
      onToggleOne,
      onMergeSelected,
      mergeSelectedDisabled: selected.size < 2,
    });

    const mergeBtn = screen.getByTestId('aisle-results-merge-selected');
    expect(mergeBtn).toBeDisabled();

    fireEvent.click(
      within(screen.getByTestId('aisle-results-select-pos-1')).getByRole('checkbox')
    );
    expect(onToggleOne).toHaveBeenCalledWith('pos-1');
    selected.add('pos-1');
    rerender(
      <I18nextProvider i18n={i18n}>
        <AisleResultsTableSection
          countedTotal={2}
          countedResultRows={2}
          mergeFeedback={null}
          onResetFilters={() => undefined}
          resetDisabled
          skuSearch=""
          onSkuSearchChange={() => undefined}
          tableSort="photo"
          onTableSortChange={() => undefined}
          filter="all"
          onFilterChange={() => undefined}
          counts={baseCounts}
          sortedForTableLength={2}
          onClearFilterOnly={() => undefined}
          tableRows={rows}
          onOpenReview={() => undefined}
          page={1}
          pageSize={25}
          totalItems={2}
          onPageChange={() => undefined}
          onPageSizeChange={() => undefined}
          selectedIds={new Set(selected)}
          onToggleOne={onToggleOne}
          onToggleAllPage={() => undefined}
          onClearSelection={() => undefined}
          onMergeSelected={onMergeSelected}
          mergeSelectedDisabled={selected.size < 2}
        />
      </I18nextProvider>
    );
    expect(screen.getByTestId('aisle-results-merge-selected')).toBeDisabled();

    fireEvent.click(
      within(screen.getByTestId('aisle-results-select-pos-2')).getByRole('checkbox')
    );
    selected.add('pos-2');
    rerender(
      <I18nextProvider i18n={i18n}>
        <AisleResultsTableSection
          countedTotal={2}
          countedResultRows={2}
          mergeFeedback={null}
          onResetFilters={() => undefined}
          resetDisabled
          skuSearch=""
          onSkuSearchChange={() => undefined}
          tableSort="photo"
          onTableSortChange={() => undefined}
          filter="all"
          onFilterChange={() => undefined}
          counts={baseCounts}
          sortedForTableLength={2}
          onClearFilterOnly={() => undefined}
          tableRows={rows}
          onOpenReview={() => undefined}
          page={1}
          pageSize={25}
          totalItems={2}
          onPageChange={() => undefined}
          onPageSizeChange={() => undefined}
          selectedIds={new Set(selected)}
          onToggleOne={onToggleOne}
          onToggleAllPage={() => undefined}
          onClearSelection={() => undefined}
          onMergeSelected={onMergeSelected}
          mergeSelectedDisabled={selected.size < 2}
        />
      </I18nextProvider>
    );
    expect(screen.getByTestId('aisle-results-merge-selected')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('aisle-results-merge-selected'));
    expect(onMergeSelected).toHaveBeenCalled();
  });

  it('supports select-all page and clear selection', () => {
    const selected = new Set<string>();
    const onToggleAllPage = vi.fn((ids: string[], select: boolean) => {
      for (const id of ids) {
        if (select) selected.add(id);
        else selected.delete(id);
      }
    });
    const onClearSelection = vi.fn(() => selected.clear());
    const rows = [
      row({ id: 'prod-a', sourcePositionId: 'pos-1' }),
      row({ id: 'prod-b', sourcePositionId: 'pos-2' }),
    ];
    const { rerender } = renderSection({
      tableRows: rows,
      selectedIds: selected,
      onToggleAllPage,
      onClearSelection,
    });

    fireEvent.click(
      within(screen.getByTestId('aisle-results-select-all')).getByRole('checkbox')
    );
    expect(onToggleAllPage).toHaveBeenCalledWith(['pos-1', 'pos-2'], true);
    selected.add('pos-1');
    selected.add('pos-2');
    rerender(
      <I18nextProvider i18n={i18n}>
        <AisleResultsTableSection
          countedTotal={2}
          countedResultRows={2}
          mergeFeedback={null}
          onResetFilters={() => undefined}
          resetDisabled
          skuSearch=""
          onSkuSearchChange={() => undefined}
          tableSort="photo"
          onTableSortChange={() => undefined}
          filter="all"
          onFilterChange={() => undefined}
          counts={baseCounts}
          sortedForTableLength={2}
          onClearFilterOnly={() => undefined}
          tableRows={rows}
          onOpenReview={() => undefined}
          page={1}
          pageSize={25}
          totalItems={2}
          onPageChange={() => undefined}
          onPageSizeChange={() => undefined}
          selectedIds={new Set(selected)}
          onToggleOne={() => undefined}
          onToggleAllPage={onToggleAllPage}
          onClearSelection={onClearSelection}
          onMergeSelected={() => undefined}
          mergeSelectedDisabled={false}
        />
      </I18nextProvider>
    );
    fireEvent.click(screen.getByTestId('aisle-results-clear-selection'));
    expect(onClearSelection).toHaveBeenCalled();
  });
});
