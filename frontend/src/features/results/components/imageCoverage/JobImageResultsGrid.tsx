/**
 * Unmatched-images queue: loading / error / empty + compact rows + pagination.
 * Only rows with has_result === false are rendered (defensive filter).
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Stack, TablePagination, Typography } from '@mui/material';
import { LoadingBlock, ErrorAlert } from '../../../../components/ui';
import JobImageResultCard from './JobImageResultCard';
import type { JobImageResultItem } from '../../../../api/types';
import { TABLE_PAGE_SIZE_OPTIONS } from '../../../../constants/dataTable';

export interface JobImageResultsGridProps {
  items: JobImageResultItem[];
  isLoading: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  onAddResult: (item: JobImageResultItem) => void;
  addResultPendingAssetId?: string | null;
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onBackToPositions?: () => void;
  pendingCount?: number | null;
}

export default function JobImageResultsGrid({
  items,
  isLoading,
  errorMessage,
  onRetry,
  onAddResult,
  addResultPendingAssetId,
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
  onBackToPositions,
  pendingCount,
}: JobImageResultsGridProps) {
  const { t } = useTranslation();
  const pendingItems = useMemo(
    () => items.filter((item) => !item.has_result && item.result_count === 0),
    [items]
  );
  const headingCount = pendingCount ?? totalItems;

  if (isLoading) {
    return <LoadingBlock message={t('results.imageCoverage.loading')} py={4} />;
  }

  if (errorMessage) {
    return <ErrorAlert message={errorMessage} onRetry={onRetry} />;
  }

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
        {t('results.imageCoverage.queue.heading', { count: headingCount })}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('results.imageCoverage.queue.description')}
      </Typography>

      {pendingItems.length === 0 ? (
        <Box data-testid="job-image-results-empty" sx={{ py: 4, textAlign: 'center' }}>
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            {t('results.imageCoverage.queue.empty')}
          </Typography>
          {onBackToPositions ? (
            <Button variant="outlined" onClick={onBackToPositions} data-testid="job-image-back-to-positions">
              {t('results.imageCoverage.queue.backToPositions')}
            </Button>
          ) : null}
        </Box>
      ) : (
        <>
          <Stack spacing={1.5} data-testid="job-image-results-list">
            {pendingItems.map((item) => (
              <JobImageResultCard
                key={item.job_source_asset_id}
                item={item}
                onAddResult={onAddResult}
                addResultDisabled={addResultPendingAssetId === item.source_asset_id}
              />
            ))}
          </Stack>
          <TablePagination
            component="div"
            count={totalItems}
            page={Math.max(0, page - 1)}
            onPageChange={(_, nextPage) => onPageChange(nextPage + 1)}
            rowsPerPage={pageSize}
            onRowsPerPageChange={(e) => onPageSizeChange(Number(e.target.value))}
            rowsPerPageOptions={[...TABLE_PAGE_SIZE_OPTIONS]}
          />
        </>
      )}
    </Box>
  );
}
