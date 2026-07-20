import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Stack, Typography } from '@mui/material';
import type { JobSummary } from '../../api/types';
import { resolveApiErrorMessage } from '../../utils/apiErrors';
import { DEFAULT_LIST_PAGE_SIZE } from '../../constants/dataTable';
import ProcessingAssetDrawer from './ProcessingAssetDrawer';
import ProcessingAssetFilters from './ProcessingAssetFilters';
import ProcessingAssetList from './ProcessingAssetList';
import ProcessingJobHeader from './ProcessingJobHeader';
import ProcessingProgressSummary from './ProcessingProgressSummary';
import { useProcessingAssetDetail, useProcessingAssets } from './hooks';
import {
  mergeProcessingFilterPatch,
  parseProcessingFilters,
  writeProcessingFilters,
  type ProcessingUrlFilters,
} from './utils/processingUrlFilters';

export interface ProcessingWorkspaceProps {
  inventoryId: string;
  aisleId: string;
  jobId: string | null;
  selectedJob: JobSummary | null;
  active: boolean;
}

export default function ProcessingWorkspace({
  inventoryId,
  aisleId,
  jobId,
  selectedJob,
  active,
}: ProcessingWorkspaceProps) {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<ProcessingUrlFilters>(() =>
    parseProcessingFilters(searchParams)
  );

  useEffect(() => {
    setFilters(parseProcessingFilters(searchParams));
  }, [searchParams]);

  const enabled = active && Boolean(inventoryId && aisleId && jobId);

  const assetsQuery = useProcessingAssets(inventoryId, aisleId, jobId ?? undefined, filters, {
    enabled,
    pageSize: DEFAULT_LIST_PAGE_SIZE,
  });

  const selectedAssetId = filters.assetId || null;
  const detailQuery = useProcessingAssetDetail(
    inventoryId,
    aisleId,
    jobId ?? undefined,
    selectedAssetId ?? undefined,
    { enabled: enabled && Boolean(selectedAssetId) }
  );

  const updateFilters = useCallback(
    (patch: Partial<ProcessingUrlFilters>, options?: { resetPage?: boolean }) => {
      setFilters((current) => {
        const next = mergeProcessingFilterPatch(current, patch, options);
        setSearchParams(writeProcessingFilters(searchParams, next), { replace: true });
        return next;
      });
    },
    [searchParams, setSearchParams]
  );

  const handleSelectAsset = useCallback(
    (assetId: string) => {
      updateFilters({ assetId });
    },
    [updateFilters]
  );

  const handleCloseDrawer = useCallback(() => {
    updateFilters({ assetId: '' });
  }, [updateFilters]);

  const handleRefresh = useCallback(async () => {
    await Promise.all([assetsQuery.refetch(), detailQuery.refetch()]);
  }, [assetsQuery, detailQuery]);

  const listErrorMessage = useMemo(() => {
    if (!assetsQuery.error) return null;
    return resolveApiErrorMessage(assetsQuery.error, 'processing.list.loadFailed');
  }, [assetsQuery.error]);

  if (!jobId) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 2 }} data-testid="processing-select-job">
        {t('processing.selectJob')}
      </Typography>
    );
  }

  return (
    <Stack spacing={2} data-testid="processing-workspace">
      <ProcessingJobHeader job={selectedJob} summary={assetsQuery.data?.summary ?? null} />
      <ProcessingProgressSummary summary={assetsQuery.data?.summary ?? null} />
      <ProcessingAssetFilters filters={filters} onChange={(patch) => updateFilters(patch, { resetPage: true })} />
      <ProcessingAssetList
        items={assetsQuery.data?.items ?? []}
        total={assetsQuery.data?.total ?? 0}
        page={filters.page}
        pageSize={assetsQuery.data?.page_size ?? DEFAULT_LIST_PAGE_SIZE}
        isLoading={assetsQuery.isLoading}
        errorMessage={listErrorMessage}
        selectedAssetId={selectedAssetId}
        onSelectAsset={handleSelectAsset}
        onPageChange={(page) => updateFilters({ page })}
        onRetry={() => void assetsQuery.refetch()}
      />
      <ProcessingAssetDrawer
        open={Boolean(selectedAssetId)}
        onClose={handleCloseDrawer}
        inventoryId={inventoryId}
        aisleId={aisleId}
        jobId={jobId}
        detail={detailQuery.data}
        isLoading={detailQuery.isLoading}
        error={detailQuery.error}
        onRetry={() => void detailQuery.refetch()}
        onRefresh={() => void handleRefresh()}
      />
    </Stack>
  );
}
