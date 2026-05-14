import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { Alert, Box, Button, Typography } from '@mui/material';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { rowMatchesSearchQuery } from '../utils/tableSearch';
import { ErrorAlert, LoadingBlock, useAppSnackbar } from '../components/ui';
import CreateAisleDialog from '../components/CreateAisleDialog';
import { useInventoryDetail, useAislesList, useCreateAisle } from '../hooks';
import { ROUTE_HOME } from '../constants/appRoutes';
import { toAisleInventoryTableRows, toInventoryHeaderViewModel } from '../features/inventories/adapters';
import { useAisleAssetUploadFlow } from '../features/inventories/hooks/useAisleAssetUploadFlow';
import { useAisleProcessingFlow } from '../features/inventories/hooks/useAisleProcessingFlow';
import AisleProcessingDialog from '../features/inventories/components/AisleProcessingDialog';
import InventoryAislesSection from '../features/inventories/components/InventoryAislesSection';
import InventoryDetailHeader from '../features/inventories/components/InventoryDetailHeader';

export default function InventoryDetail() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const navigate = useNavigate();
  const { showSnackbar } = useAppSnackbar();
  const [createAisleOpen, setCreateAisleOpen] = useState(false);
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
    onBeforeUploadAttempt: () => setProcessError(null),
  });

  const processFlow = useAisleProcessingFlow({
    inventoryId: inventoryId ?? '',
    isProductionInventory,
    processError,
    setProcessError,
    onBeforeProcessMutation: () => setUploadError(null),
  });

  const aisles = useMemo(() => aislesQuery.data?.items ?? [], [aislesQuery.data?.items]);

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
  };

  return (
    <>
      {inventoryLoading && !inventory ? (
        <LoadingBlock />
      ) : inventoryError && !inventory ? (
        <>
          <ErrorAlert error={inventoryQuery.error} context="inventory" onRetry={() => inventoryQuery.refetch()} />
          <Button sx={{ mt: 2 }} onClick={() => navigate(ROUTE_HOME)}>
            {t('inventory.back_to_list')}
          </Button>
        </>
      ) : inventory && headerVm ? (
        <>
          <InventoryDetailHeader
            inventory={inventory}
            inventoryId={inventoryId ?? ''}
            headerVm={headerVm}
            onOpenCreateAisle={() => setCreateAisleOpen(true)}
          />
          <Box sx={{ display: 'grid', gap: 2 }}>
            {!inventory.client_id ? (
              <Alert severity="warning" data-testid="inventory-legacy-no-client">
                {t('inventory.legacy_no_client_warning')}
              </Alert>
            ) : null}
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

            {aislesError ? (
              <ErrorAlert error={aislesQuery.error} context="aisle" onRetry={() => aislesQuery.refetch()} />
            ) : null}

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
              onRequestUpload={uploadFlow.beginUploadForAisle}
              onRequestProcess={(id, code, clientSupplierId) =>
                void processFlow.requestProcess(id, code, clientSupplierId)
              }
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
        clientSupplierId={processFlow.dialogTarget?.clientSupplierId ?? null}
        providerKey={processFlow.providerKey}
        onProviderKeyChange={processFlow.setProviderKey}
        modelKey={processFlow.modelKey}
        onModelKeyChange={processFlow.setModelKey}
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
        inventoryClientId={inventory?.client_id ?? null}
        onClose={() => setCreateAisleOpen(false)}
        onSuccess={handleCreateAisleSuccess}
        existingAisleCodes={aisles.map((a) => a.code)}
        createAisleFn={createAisleMutation.mutateAsync}
      />

    </>
  );
}
