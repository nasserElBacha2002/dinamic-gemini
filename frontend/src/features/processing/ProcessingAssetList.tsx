import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Stack, Typography } from '@mui/material';
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';
import { DataTable, ErrorAlert, LoadingBlock, StatusBadge, type DataTableColumn } from '../../components/ui';
import type { AssetProcessingSummary } from '../../api/types/processing';
import {
  formatDurationMs,
  processingErrorCodeMessage,
  processingStatusLabel,
  processingStatusToSemantic,
  shortAssetId,
} from './utils/processingStatus';

export interface ProcessingAssetListProps {
  items: AssetProcessingSummary[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  errorMessage?: string | null;
  selectedAssetId?: string | null;
  onSelectAsset: (assetId: string) => void;
  onPageChange: (page: number) => void;
  onRetry?: () => void;
}

function AssetRowSignals({ item, t }: { item: AssetProcessingSummary; t: ReturnType<typeof useTranslation>['t'] }) {
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
      {item.has_fallback ? (
        <Typography variant="caption" color="warning.main">
          {t('processing.list.fallback')}
        </Typography>
      ) : null}
      {item.has_manual_result ? (
        <Typography variant="caption" color="info.main">
          {t('processing.list.manual')}
        </Typography>
      ) : null}
      {item.warnings.length > 0 ? (
        <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
          <WarningAmberOutlinedIcon sx={{ fontSize: 14, color: 'warning.main' }} aria-hidden />
          <Typography variant="caption" color="warning.main">
            {t('processing.list.warningsCount', { count: item.warnings.length })}
          </Typography>
        </Box>
      ) : null}
    </Stack>
  );
}

export default function ProcessingAssetList({
  items,
  total,
  page,
  pageSize,
  isLoading,
  errorMessage,
  selectedAssetId,
  onSelectAsset,
  onPageChange,
  onRetry,
}: ProcessingAssetListProps) {
  const { t } = useTranslation();

  const columns = useMemo((): DataTableColumn<AssetProcessingSummary>[] => [
      {
        id: 'file',
        label: t('processing.list.file'),
        cell: (row: AssetProcessingSummary) => row.file_name || shortAssetId(row.asset_id),
      },
      {
        id: 'status',
        label: t('processing.list.status'),
        cell: (row: AssetProcessingSummary) => (
          <StatusBadge
            label={processingStatusLabel(row.status, t)}
            semantic={processingStatusToSemantic(row.status)}
          />
        ),
      },
      {
        id: 'strategy',
        label: t('processing.list.strategy'),
        cell: (row: AssetProcessingSummary) => row.executed_strategy || t('common.em_dash'),
      },
      {
        id: 'result',
        label: t('processing.list.result'),
        cell: (row: AssetProcessingSummary) =>
          row.internal_code
            ? `${row.internal_code}${row.quantity != null ? ` × ${row.quantity}` : ''}`
            : t('common.em_dash'),
      },
      {
        id: 'duration',
        label: t('processing.list.duration'),
        cell: (row: AssetProcessingSummary) => formatDurationMs(row.duration_ms, t),
      },
      {
        id: 'signals',
        label: t('processing.list.signals'),
        cell: (row: AssetProcessingSummary) => <AssetRowSignals item={row} t={t} />,
      },
      {
        id: 'actions',
        label: t('processing.list.actions'),
        cell: (row: AssetProcessingSummary) => (
          <Button size="small" variant="outlined" onClick={() => onSelectAsset(row.asset_id)}>
            {t('processing.list.viewDetail')}
          </Button>
        ),
      },
    ],
    [onSelectAsset, t]
  );

  if (isLoading) {
    return <LoadingBlock message={t('processing.list.loading')} py={4} />;
  }

  if (errorMessage) {
    return <ErrorAlert message={errorMessage} onRetry={onRetry} />;
  }

  return (
    <DataTable
      rows={items}
      rowKey={(row) => row.asset_id}
      columns={columns}
      emptyState={{ message: t('processing.list.empty') }}
      pagination={{
        page,
        pageSize,
        totalItems: total,
        onPageChange,
      }}
      mobile={{
        mode: 'card',
        title: (row) => row.file_name || shortAssetId(row.asset_id),
        subtitle: (row) => row.executed_strategy || t('common.em_dash'),
        status: (row) => (
          <StatusBadge
            label={processingStatusLabel(row.status, t)}
            semantic={processingStatusToSemantic(row.status)}
          />
        ),
        fields: [
          {
            id: 'result',
            label: t('processing.list.result'),
            value: (row) =>
              row.internal_code
                ? `${row.internal_code}${row.quantity != null ? ` × ${row.quantity}` : ''}`
                : t('common.em_dash'),
          },
          {
            id: 'error',
            label: t('processing.list.error'),
            value: (row) => processingErrorCodeMessage(row.last_error_code, t),
            hidden: (row) => !row.last_error_code,
          },
          {
            id: 'duration',
            label: t('processing.list.duration'),
            value: (row) => formatDurationMs(row.duration_ms, t),
          },
        ],
        primaryAction: (row) => (
          <Button
            size="small"
            variant={selectedAssetId === row.asset_id ? 'contained' : 'outlined'}
            onClick={() => onSelectAsset(row.asset_id)}
            fullWidth
          >
            {t('processing.list.viewDetail')}
          </Button>
        ),
        ariaLabel: (row) => row.file_name || row.asset_id,
      }}
      testId="processing-asset-list"
    />
  );
}
