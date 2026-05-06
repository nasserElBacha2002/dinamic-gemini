import { useTranslation } from 'react-i18next';
import { DataTable, FilterToolbar, SectionCard, TableSearchField, type DataTableColumn } from '../../../components/ui';
import type { InventoryPerformanceRow } from '../types';

export interface MetricsInventoryPerformanceSectionProps {
  search: string;
  onSearchChange: (value: string) => void;
  onResetSearch: () => void;
  rows: readonly InventoryPerformanceRow[];
  columns: readonly DataTableColumn<InventoryPerformanceRow>[];
  isLoading: boolean;
  sortBy: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (sortBy: string, sortDir: 'asc' | 'desc') => void;
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function MetricsInventoryPerformanceSection({
  search,
  onSearchChange,
  onResetSearch,
  rows,
  columns,
  isLoading,
  sortBy,
  sortDir,
  onSortChange,
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
}: MetricsInventoryPerformanceSectionProps) {
  const { t } = useTranslation();

  return (
    <SectionCard title={t('analytics.inventory_performance_title')} subtitle={t('analytics.inventory_performance_subtitle')}>
      <FilterToolbar onReset={onResetSearch} resetDisabled={!search.trim()}>
        <TableSearchField
          label={t('table.search_label')}
          placeholder={t('analytics.search_inventory_performance_placeholder')}
          value={search}
          onChange={onSearchChange}
          data-testid="metrics-inventory-performance-search"
        />
      </FilterToolbar>
      <DataTable<InventoryPerformanceRow>
        rows={rows}
        rowKey={(r) => r.inventory_id}
        columns={columns}
        loading={isLoading}
        sort={{
          sortBy,
          sortDir,
          onSortChange,
        }}
        pagination={{
          page,
          pageSize,
          totalItems,
          onPageChange,
          onPageSizeChange,
        }}
        emptyState={
          search.trim() && !isLoading && totalItems === 0
            ? { message: t('table.empty_no_match') }
            : { message: t('analytics.empty_inventory_performance') }
        }
      />
    </SectionCard>
  );
}
