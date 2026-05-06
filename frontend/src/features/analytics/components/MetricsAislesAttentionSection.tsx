import { useTranslation } from 'react-i18next';
import { DataTable, FilterToolbar, SectionCard, TableSearchField, type DataTableColumn } from '../../../components/ui';
import type { AisleIssueRow } from '../types';

export interface MetricsAislesAttentionSectionProps {
  search: string;
  onSearchChange: (value: string) => void;
  onResetSearch: () => void;
  rows: readonly AisleIssueRow[];
  columns: readonly DataTableColumn<AisleIssueRow>[];
  isLoading: boolean;
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function MetricsAislesAttentionSection({
  search,
  onSearchChange,
  onResetSearch,
  rows,
  columns,
  isLoading,
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
}: MetricsAislesAttentionSectionProps) {
  const { t } = useTranslation();

  return (
    <SectionCard title={t('analytics.aisles_attention_title')} subtitle={t('analytics.aisles_attention_subtitle')}>
      <FilterToolbar onReset={onResetSearch} resetDisabled={!search.trim()}>
        <TableSearchField
          label={t('table.search_label')}
          placeholder={t('analytics.search_aisle_metrics_placeholder')}
          value={search}
          onChange={onSearchChange}
          data-testid="metrics-aisle-issues-search"
        />
      </FilterToolbar>
      <DataTable<AisleIssueRow>
        rows={rows}
        rowKey={(r) => `${r.inventory_id}-${r.aisle_id}`}
        columns={columns}
        loading={isLoading}
        size="small"
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
            : { message: t('analytics.empty_aisle_metrics') }
        }
      />
    </SectionCard>
  );
}
