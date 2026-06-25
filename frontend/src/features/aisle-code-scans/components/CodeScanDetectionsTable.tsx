import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Typography } from '@mui/material';
import type { CodeScanDetection } from '../../../api/types/codeScans';
import { DataTable, type DataTableColumn } from '../../../components/ui';
import { useTableState } from '../../../hooks';
import { formatDate } from '../../../utils/formatDate';
import {
  formatCodeScanCodeType,
  formatCodeScanDetectionStatus,
  formatCodeScanMatchType,
} from '../formatters';
import CodeScanAssetPreviewButton from './CodeScanAssetPreviewButton';
import CodeScanMatchStatusChip from './CodeScanMatchStatusChip';
import CopyCodeValueButton from './CopyCodeValueButton';

export interface CodeScanDetectionsTableProps {
  detections: CodeScanDetection[];
  inventoryId: string;
  aisleId: string;
  jobIdForPreview?: string | null;
}

export default function CodeScanDetectionsTable({
  detections,
  inventoryId,
  aisleId,
  jobIdForPreview,
}: CodeScanDetectionsTableProps) {
  const { t } = useTranslation();
  const { page, pageSize, setPage, setPageSize } = useTableState();

  const columns = useMemo((): DataTableColumn<CodeScanDetection>[] => [
    {
      id: 'type',
      label: t('aisleCodeScans.tables.type'),
      cell: (row) => formatCodeScanCodeType(t, row.code_type),
    },
    {
      id: 'value',
      label: t('aisleCodeScans.tables.value'),
      cell: (row) => (
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.5, maxWidth: 240 }}>
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
      id: 'status',
      label: t('aisleCodeScans.tables.status'),
      cell: (row) => formatCodeScanDetectionStatus(t, row.detection_status),
    },
    {
      id: 'match_status',
      label: t('aisleCodeScans.matching.status'),
      cell: (row) => <CodeScanMatchStatusChip status={row.match_status} />,
    },
    {
      id: 'match_type',
      label: t('aisleCodeScans.matching.matchType'),
      cell: (row) => formatCodeScanMatchType(t, row.match_type),
    },
    {
      id: 'linked_result',
      label: t('aisleCodeScans.matching.linkedResult'),
      cell: (row) => (
        <Box component="span" sx={{ wordBreak: 'break-all' }}>
          {row.matched_position_id ?? '—'}
        </Box>
      ),
    },
    {
      id: 'source_asset',
      label: t('aisleCodeScans.tables.sourceAsset'),
      cell: (row) => (
        <Box component="span" sx={{ wordBreak: 'break-all' }}>
          {row.asset_id}
        </Box>
      ),
    },
    {
      id: 'engine',
      label: t('aisleCodeScans.summary.engine'),
      cell: (row) => row.scanner_engine,
    },
    {
      id: 'date',
      label: t('aisleCodeScans.tables.date'),
      cell: (row) => formatDate(row.created_at),
    },
    {
      id: 'actions',
      label: t('common.actions'),
      align: 'right',
      cell: (row) => (
        <CodeScanAssetPreviewButton
          inventoryId={inventoryId}
          aisleId={aisleId}
          assetId={row.asset_id}
          jobIdForPreview={jobIdForPreview}
        />
      ),
    },
  ], [aisleId, inventoryId, jobIdForPreview, t]);

  const paginatedDetections = useMemo(() => {
    const start = (page - 1) * pageSize;
    return detections.slice(start, start + pageSize);
  }, [detections, page, pageSize]);

  if (!detections.length) return null;

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('aisleCodeScans.tables.detectionsSection')}
      </Typography>
      <DataTable
        rows={paginatedDetections}
        rowKey={(row) => row.id}
        columns={columns}
        stickyHeader={false}
        pagination={{
          page,
          pageSize,
          totalItems: detections.length,
          onPageChange: setPage,
          onPageSizeChange: setPageSize,
        }}
      />
    </Box>
  );
}
