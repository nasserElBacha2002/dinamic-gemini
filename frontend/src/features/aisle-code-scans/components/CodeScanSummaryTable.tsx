import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Typography } from '@mui/material';
import type { CodeScanSummaryItem } from '../../../api/types/codeScans';
import { DataTable, type DataTableColumn } from '../../../components/ui';
import { useTableState } from '../../../hooks';
import { formatDate } from '../../../utils/formatDate';
import { formatCodeScanCodeType } from '../formatters';
import CodeScanMatchStatusChip from './CodeScanMatchStatusChip';
import CopyCodeValueButton from './CopyCodeValueButton';

export interface CodeScanSummaryTableProps {
  items: CodeScanSummaryItem[];
}

export default function CodeScanSummaryTable({ items }: CodeScanSummaryTableProps) {
  const { t } = useTranslation();
  const { page, pageSize, setPage, setPageSize } = useTableState();

  useEffect(() => {
    setPage(1);
  }, [items.length, setPage]);

  const columns = useMemo((): DataTableColumn<CodeScanSummaryItem>[] => [
    {
      id: 'type',
      label: t('aisleCodeScans.tables.type'),
      cell: (row) => formatCodeScanCodeType(t, row.code_type),
    },
    {
      id: 'value',
      label: t('aisleCodeScans.tables.value'),
      cell: (row) => (
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.5, maxWidth: 280 }}>
          <Typography
            variant="body2"
            component="span"
            sx={{ wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}
          >
            {row.code_value}
          </Typography>
          <CopyCodeValueButton value={row.code_value} />
        </Box>
      ),
    },
    {
      id: 'occurrences',
      label: t('aisleCodeScans.tables.occurrences'),
      align: 'right',
      cell: (row) => row.occurrences,
    },
    {
      id: 'assets',
      label: t('aisleCodeScans.tables.assets'),
      cell: (row) => (
        <Box component="span" sx={{ wordBreak: 'break-all' }}>
          {row.asset_ids.join(', ')}
        </Box>
      ),
    },
    {
      id: 'first_seen',
      label: t('aisleCodeScans.tables.firstSeenAt'),
      cell: (row) => formatDate(row.first_seen_at),
    },
    {
      id: 'match_status',
      label: t('aisleCodeScans.matching.status'),
      cell: (row) => <CodeScanMatchStatusChip status={row.match_status} />,
    },
    {
      id: 'linked_result',
      label: t('aisleCodeScans.matching.linkedResult'),
      cell: (row) => (
        <Box component="span" sx={{ wordBreak: 'break-all' }}>
          {row.matched_position_ids?.length ? row.matched_position_ids.join(', ') : '—'}
        </Box>
      ),
    },
  ], [t]);

  const paginatedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize]);

  if (!items.length) return null;

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('aisleCodeScans.tables.summarySection')}
      </Typography>
      <DataTable
        rows={paginatedItems}
        rowKey={(row) => `${row.normalized_code_value}-${row.code_type}`}
        columns={columns}
        stickyHeader={false}
        mobile={{
          mode: 'card',
          title: (row) => row.code_value,
          status: (row) => <CodeScanMatchStatusChip status={row.match_status} />,
          ariaLabel: (row) => row.code_value,
          fields: [
            {
              id: 'type',
              label: t('aisleCodeScans.tables.type'),
              value: (row) => formatCodeScanCodeType(t, row.code_type),
            },
            {
              id: 'occurrences',
              label: t('aisleCodeScans.tables.occurrences'),
              value: (row) => row.occurrences,
            },
            {
              id: 'assets',
              label: t('aisleCodeScans.tables.assets'),
              value: (row) => row.asset_ids.join(', '),
              fullWidth: true,
            },
            {
              id: 'first_seen',
              label: t('aisleCodeScans.tables.firstSeenAt'),
              value: (row) => formatDate(row.first_seen_at),
            },
            {
              id: 'linked_result',
              label: t('aisleCodeScans.matching.linkedResult'),
              value: (row) =>
                row.matched_position_ids?.length ? row.matched_position_ids.join(', ') : t('common.em_dash'),
              fullWidth: true,
            },
          ],
        }}
        pagination={{
          page,
          pageSize,
          totalItems: items.length,
          onPageChange: setPage,
          onPageSizeChange: setPageSize,
        }}
      />
    </Box>
  );
}
