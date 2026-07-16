/**
 * Job image coverage grid: loading / error / empty states + cards + pagination.
 */

import { useTranslation } from 'react-i18next';
import { Box, Stack, TablePagination } from '@mui/material';
import { LoadingBlock, ErrorAlert } from '../../../../components/ui';
import ResultsEmptyState from '../ResultsEmptyState';
import JobImageResultCard from './JobImageResultCard';
import type { JobImageResultItem } from '../../../../api/types';
import { TABLE_PAGE_SIZE_OPTIONS } from '../../../../constants/dataTable';

export interface JobImageResultsGridProps {
  inventoryId: string;
  aisleId: string;
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
}

export default function JobImageResultsGrid({
  inventoryId,
  aisleId,
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
}: JobImageResultsGridProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return <LoadingBlock message={t('results.imageCoverage.loading')} py={4} />;
  }

  if (errorMessage) {
    return <ErrorAlert message={errorMessage} onRetry={onRetry} />;
  }

  if (items.length === 0) {
    return <ResultsEmptyState message={t('results.imageCoverage.empty')} />;
  }

  return (
    <Box>
      <Stack spacing={1.5} data-testid="job-image-results-list">
        {items.map((item) => (
          <JobImageResultCard
            key={item.job_source_asset_id}
            inventoryId={inventoryId}
            aisleId={aisleId}
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
    </Box>
  );
}
