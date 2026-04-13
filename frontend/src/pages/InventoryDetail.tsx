import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Button, Typography } from '@mui/material';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { rowMatchesSearchQuery } from '../utils/tableSearch';
import { ErrorAlert, LoadingBlock, useAppSnackbar } from '../components/ui';
import AisleObservabilityDialog from '../components/AisleObservabilityDialog';
import CreateAisleDialog from '../components/CreateAisleDialog';
import { useInventoryDetail, useAislesList, useCreateAisle } from '../hooks';
import { toAisleInventoryTableRows, toInventoryHeaderViewModel } from '../features/inventories/adapters';
import { useAisleAssetUploadFlow } from '../features/inventories/hooks/useAisleAssetUploadFlow';
import { useAisleProcessingFlow } from '../features/inventories/hooks/useAisleProcessingFlow';
import AisleProcessingDialog from '../features/inventories/components/AisleProcessingDialog';
import InventoryAislesSection from '../features/inventories/components/InventoryAislesSection';
import InventoryReferenceImagesModule from '../features/inventories/components/InventoryReferenceImagesModule';
import InventoryDetailHeader from '../features/inventories/components/InventoryDetailHeader';

export default function InventoryDetail() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
  const [observabilityDialog, setObservabilityDialog] = useState<{
    aisleId: string;
    aisleCode: string;
    initialSelectedRunId: string | null;
  } | null>(null);
  const [aisleTableSearch, setAisleTableSearch] = useState('');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [processError, setProcessError] = useState<string | null>(null);

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, { enabled: Boolean(inventoryId && inventoryQuery.data) });

  const inventory = inventoryQuery.data ?? null;
  const isProductionInventory = (inventory?.processing_mode ?? 'production') !== 'test';

  const uploadFlow = useAisleAssetUploadFlow({
    inventoryId: inventoryId ?? '',
    uploadError,
    setUploadError,
    onAfterSuccess: () => void aislesQuery.refetch(),
    onBeforeUploadAttempt: () => setProcessError(null),
  });

  const processFlow = useAisleProcessingFlow({
    inventoryId: inventoryId ?? '',
    isProductionInventory,
    processError,
    setProcessError,
    onAfterSuccess: () => void aislesQuery.refetch(),
    onBeforeProcessMutation: () => setUploadError(null),
  });

  const aisles = aislesQuery.data?.items ?? [];
  const emptyDash = t('common.em_dash');
  const tableRows = useMemo(() => toAisleInventoryTableRows(aisles, emptyDash), [aisles, emptyDash]);
  const filteredTableRows = useMemo(() => {
    const matchingIds = new Set(
      aisles
        .filter((a) => rowMatchesSearchQuery(aisleTableSearch, [a.code, a.status, a.id]))
        .map((a) => a.id)
    );
    return tableRows.filter((row) => matchingIds.has(row.presentation.id));
  }, [aisles, aisleTableSearch, tableRows]);

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
              <InventoryDetailHeader
                inventory={inventory}
                inventoryId={inventoryId ?? ''}
                headerVm={headerVm}
                onOpenReferenceImages={openReferenceImages}
                onOpenCreateAisle={() => setCreateAisleOpen(true)}
              />
              <Box sx={{ display: 'grid', gap: 2 }}>
                {processError ? (
                  <Box data-testid="inventory-process-error">
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                      {t('aisle.process_error_label')}
                    </Typography>
                    <ErrorAlert message={processError} onClose={() => setProcessError(null)} />
                  </Box>
                ) : null}

                {uploadError ? (
                  <Box data-testid="inventory-upload-error">
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                      {t('aisle.upload_error_label')}
                    </Typography>
                    <ErrorAlert message={uploadError} onClose={() => setUploadError(null)} />
                  </Box>
                ) : null}

                {aislesError ? <ErrorAlert message={aislesError} onRetry={() => aislesQuery.refetch()} /> : null}

                <InventoryAislesSection
                  inventoryId={inventoryId ?? ''}
                  tableRows={tableRows}
                  filteredTableRows={filteredTableRows}
                  aislesLoading={aislesLoading}
                  aisleTableSearch={aisleTableSearch}
                  onAisleTableSearch={setAisleTableSearch}
                  onRefreshAisles={() => void aislesQuery.refetch()}
                  fileInputRef={uploadFlow.fileInputRef}
                  onFileInputChange={uploadFlow.handleNativeFileInputChange}
                  onOpenObservability={(p) =>
                    setObservabilityDialog({
                      aisleId: p.aisleId,
                      aisleCode: p.aisleCode,
                      initialSelectedRunId: p.initialSelectedRunId,
                    })
                  }
                  onRequestUpload={uploadFlow.beginUploadForAisle}
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
              key={`${observabilityDialog.aisleId}-${observabilityDialog.initialSelectedRunId ?? 'none'}`}
              open
              inventoryId={inventoryId}
              aisleId={observabilityDialog.aisleId}
              aisleCode={observabilityDialog.aisleCode}
              initialSelectedJobId={observabilityDialog.initialSelectedRunId}
              onClose={() => setObservabilityDialog(null)}
              onAislesInvalidate={() => aislesQuery.refetch()}
            />
          ) : null}
        </>
      )}
    </InventoryReferenceImagesModule>
  );
}
