import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Button, Typography } from '@mui/material';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { rowMatchesSearchQuery } from '../utils/tableSearch';
import { exportInventoryResultsCsv } from '../api/client';
import { ErrorAlert, LoadingBlock, StatusBadge, useAppSnackbar } from '../components/ui';
import { PageHeader } from '../components/shell';
import AisleObservabilityDialog from '../components/AisleObservabilityDialog';
import CreateAisleDialog from '../components/CreateAisleDialog';
import { useInventoryDetail, useAislesList, useCreateAisle } from '../hooks';
import { toAisleInventoryRowViewModels, toInventoryHeaderViewModel } from '../features/inventories/adapters';
import { useAisleAssetUploadFlow } from '../features/inventories/hooks/useAisleAssetUploadFlow';
import { useAisleProcessingFlow } from '../features/inventories/hooks/useAisleProcessingFlow';
import AisleProcessingDialog from '../features/inventories/components/AisleProcessingDialog';
import InventoryAislesSection from '../features/inventories/components/InventoryAislesSection';
import InventoryReferenceImagesModule from '../features/inventories/components/InventoryReferenceImagesModule';

export default function InventoryDetail() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
  const [observabilityDialog, setObservabilityDialog] = useState<{
    aisleId: string;
    aisleCode: string;
    initialSelectedJobId: string | null;
  } | null>(null);
  const [exportingCsv, setExportingCsv] = useState(false);
  const [aisleTableSearch, setAisleTableSearch] = useState('');

  const clearUploadErrorRef = useRef<() => void>(() => {});
  const clearProcessErrorRef = useRef<() => void>(() => {});

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, { enabled: Boolean(inventoryId && inventoryQuery.data) });

  const inventory = inventoryQuery.data ?? null;
  const isProductionInventory = (inventory?.processing_mode ?? 'production') !== 'test';

  const uploadFlow = useAisleAssetUploadFlow({
    inventoryId: inventoryId ?? '',
    onAfterSuccess: () => void aislesQuery.refetch(),
    onBeforeUpload: () => clearProcessErrorRef.current(),
  });

  const processFlow = useAisleProcessingFlow({
    inventoryId: inventoryId ?? '',
    isProductionInventory,
    onAfterSuccess: () => void aislesQuery.refetch(),
    onBeforeProcessMutation: () => clearUploadErrorRef.current(),
  });

  clearUploadErrorRef.current = () => uploadFlow.setUploadError(null);
  clearProcessErrorRef.current = () => processFlow.setProcessError(null);

  const aisles = aislesQuery.data?.items ?? [];
  const emptyDash = t('common.em_dash');
  const rowViewModels = useMemo(
    () => toAisleInventoryRowViewModels(aisles, emptyDash),
    [aisles, emptyDash]
  );
  const filteredRowViewModels = useMemo(() => {
    const matchingIds = new Set(
      aisles
        .filter((a) => rowMatchesSearchQuery(aisleTableSearch, [a.code, a.status, a.id]))
        .map((a) => a.id)
    );
    return rowViewModels.filter((row) => matchingIds.has(row.id));
  }, [aisles, aisleTableSearch, rowViewModels]);

  const createAisleMutation = useCreateAisle(inventoryId ?? '');

  const inventoryLoading = inventoryQuery.isLoading;
  const inventoryError =
    inventoryQuery.isError && inventoryQuery.error
      ? inventoryQuery.error instanceof ApiError && inventoryQuery.error.status === 404
        ? t('inventory.not_found')
        : resolveApiErrorMessage(inventoryQuery.error, 'errors.load_inventory')
      : null;

  const aislesLoading = aislesQuery.isLoading;
  const aislesError =
    aislesQuery.isError && aislesQuery.error
      ? resolveApiErrorMessage(aislesQuery.error, 'errors.load_aisles')
      : null;

  const headerVm = inventory ? toInventoryHeaderViewModel(inventory, t) : null;

  const handleCreateAisleSuccess = () => {
    showSnackbar(t('aisle.aisle_created_snackbar'), 'success');
    void aislesQuery.refetch();
  };

  return (
    <InventoryReferenceImagesModule
      inventoryId={inventoryId ?? ''}
      inventoryReady={Boolean(inventoryQuery.data)}
    >
      {({ openReferenceImages }) => (
        <>
          {inventoryLoading && !inventory ? (
            <LoadingBlock />
          ) : inventoryError && !inventory ? (
            <>
              <ErrorAlert message={inventoryError} onRetry={() => inventoryQuery.refetch()} />
              <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>
                {t('inventory.back_to_list')}
              </Button>
            </>
          ) : inventory && headerVm ? (
            <>
              <PageHeader
                breadcrumbs={[{ label: t('aisle.breadcrumb_inventories'), to: '/' }]}
                title={headerVm.title}
                subtitle={
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1 }}>
                      <StatusBadge label={headerVm.statusLabel} semantic={headerVm.statusSemantic} />
                      <StatusBadge
                        label={headerVm.processingModeLabel}
                        semantic={headerVm.processingModeSemantic}
                      />
                    </Box>
                    {headerVm.primaryConfigCaption ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        {headerVm.primaryConfigCaption}
                      </Typography>
                    ) : null}
                    <Box component="span" sx={{ color: 'text.secondary', typography: 'caption' }}>
                      {headerVm.createdDateCaption}
                    </Box>
                  </Box>
                }
                actions={
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
                    <Button variant="outlined" size="small" onClick={openReferenceImages}>
                      {t('aisle.visual_refs_title')}
                    </Button>
                    {inventory.processing_mode === 'test' ? (
                      <Button
                        variant="outlined"
                        size="small"
                        data-testid="inventory-header-compare-runs"
                        onClick={() => navigate(`/inventories/${inventoryId}/analytics/compare`)}
                      >
                        {t('analytics.compare_runs_link')}
                      </Button>
                    ) : null}
                    <Button
                      variant="outlined"
                      size="small"
                      disabled={!inventoryId || exportingCsv}
                      onClick={async () => {
                        if (!inventoryId) return;
                        setExportingCsv(true);
                        try {
                          await exportInventoryResultsCsv(inventoryId);
                        } catch (e) {
                          const err = e instanceof ApiError ? e : new ApiError(String(e));
                          showSnackbar(resolveApiErrorMessage(err, 'errors.export_failed'), 'error');
                        } finally {
                          setExportingCsv(false);
                        }
                      }}
                    >
                      {exportingCsv ? t('common.exporting') : t('aisle.export_csv')}
                    </Button>
                    <Button variant="contained" size="small" onClick={() => setCreateAisleOpen(true)}>
                      {t('aisle.create')}
                    </Button>
                  </Box>
                }
              />
              <Box sx={{ display: 'grid', gap: 2 }}>
                {processFlow.processError ? (
                  <Box data-testid="inventory-process-error">
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                      {t('aisle.process_error_label')}
                    </Typography>
                    <ErrorAlert
                      message={processFlow.processError}
                      onClose={() => processFlow.setProcessError(null)}
                    />
                  </Box>
                ) : null}

                {uploadFlow.uploadError ? (
                  <Box data-testid="inventory-upload-error">
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                      {t('aisle.upload_error_label')}
                    </Typography>
                    <ErrorAlert
                      message={uploadFlow.uploadError}
                      onClose={() => uploadFlow.setUploadError(null)}
                    />
                  </Box>
                ) : null}

                {aislesError ? <ErrorAlert message={aislesError} onRetry={() => aislesQuery.refetch()} /> : null}

                <InventoryAislesSection
                  inventoryId={inventoryId ?? ''}
                  rowViewModels={rowViewModels}
                  filteredRowViewModels={filteredRowViewModels}
                  aislesLoading={aislesLoading}
                  aisleTableSearch={aisleTableSearch}
                  onAisleTableSearch={setAisleTableSearch}
                  onRefreshAisles={() => void aislesQuery.refetch()}
                  fileInputRef={uploadFlow.fileInputRef}
                  onFileInputChange={uploadFlow.handleFileInputChange}
                  onOpenObservability={setObservabilityDialog}
                  onRequestUpload={uploadFlow.openPickerForAisle}
                  onRequestProcess={(id, code) => void processFlow.requestProcess(id, code)}
                  aislesDataLoaded={Boolean(aislesQuery.data)}
                  processingAisleId={processFlow.processingAisleId}
                  uploadingAisleId={uploadFlow.uploadingAisleId}
                  onOpenCreateAisle={() => setCreateAisleOpen(true)}
                />
              </Box>
            </>
          ) : null}

          <AisleProcessingDialog
            open={Boolean(processFlow.dialogTarget)}
            aisleCode={processFlow.dialogTarget?.aisleCode ?? null}
            providerKey={processFlow.providerKey}
            onProviderKeyChange={processFlow.setProviderKey}
            modelKey={processFlow.modelKey}
            onModelKeyChange={processFlow.setModelKey}
            promptKey={processFlow.promptKey}
            onPromptKeyChange={processFlow.setPromptKey}
            providerOptsQuery={processFlow.providerOptsQuery}
            providerConfig={processFlow.providerConfig}
            onClose={processFlow.closeDialog}
            onConfirm={() => void processFlow.confirmDialog()}
            confirmDisabled={
              processFlow.processingAisleId === processFlow.dialogTarget?.aisleId ||
              (processFlow.providerOptsQuery.isLoading && processFlow.providerKey.trim() !== '')
            }
            confirmBusyLabel={processFlow.processingAisleId === processFlow.dialogTarget?.aisleId}
          />

          <CreateAisleDialog
            open={createAisleOpen}
            inventoryId={inventoryId ?? ''}
            onClose={() => setCreateAisleOpen(false)}
            onSuccess={handleCreateAisleSuccess}
            existingAisleCodes={aisles.map((a) => a.code)}
            createAisleFn={createAisleMutation.mutateAsync}
          />

          {observabilityDialog && inventoryId ? (
            <AisleObservabilityDialog
              key={`${observabilityDialog.aisleId}-${observabilityDialog.initialSelectedJobId ?? 'none'}`}
              open
              inventoryId={inventoryId}
              aisleId={observabilityDialog.aisleId}
              aisleCode={observabilityDialog.aisleCode}
              initialSelectedJobId={observabilityDialog.initialSelectedJobId}
              onClose={() => setObservabilityDialog(null)}
              onAislesInvalidate={() => aislesQuery.refetch()}
            />
          ) : null}
        </>
      )}
    </InventoryReferenceImagesModule>
  );
}
