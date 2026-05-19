import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAppSnackbar } from '../../../components/ui';
import { useProcessingProviderOptions, useStartAisleProcessing } from '../../../hooks';
import {
  hasProductionProviders,
  initialProcessingSelection,
  modelKeyForProviderChange,
  type ProcessingProviderOptionsMode,
} from '../utils/processingProviderSelection';

export interface UseAisleProcessingFlowOptions {
  inventoryId: string;
  isProductionInventory: boolean;
  processError?: string | null;
  setProcessError?: (message: string | null) => void;
  onAfterSuccess?: () => void;
  onBeforeProcessMutation?: () => void;
}

export interface AisleProcessingDialogTarget {
  aisleId: string;
  aisleCode: string;
  clientSupplierId: string | null;
}

export function useAisleProcessingFlow({
  inventoryId,
  isProductionInventory,
  processError: controlledError,
  setProcessError: controlledSetError,
  onAfterSuccess,
  onBeforeProcessMutation,
}: UseAisleProcessingFlowOptions) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();

  const [internalError, setInternalError] = useState<string | null>(null);
  const controlled = controlledSetError !== undefined;
  const processError = controlled ? (controlledError ?? null) : internalError;
  const setProcessError = controlled ? controlledSetError! : setInternalError;

  const [processingAisleId, setProcessingAisleId] = useState<string | null>(null);
  const [dialogTarget, setDialogTarget] = useState<AisleProcessingDialogTarget | null>(null);
  const [providerKey, setProviderKey] = useState('');
  const [modelKey, setModelKey] = useState('');
  const [selectionInitialized, setSelectionInitialized] = useState(false);

  const optionsMode: ProcessingProviderOptionsMode = isProductionInventory
    ? 'production'
    : 'test';

  const processMutation = useStartAisleProcessing(inventoryId);
  const providerOptsQuery = useProcessingProviderOptions({
    enabled: Boolean(dialogTarget && inventoryId),
    mode: optionsMode,
  });

  useEffect(() => {
    if (!dialogTarget || selectionInitialized || !providerOptsQuery.data) {
      return;
    }
    const { providerKey: p, modelKey: m } = initialProcessingSelection(
      providerOptsQuery.data,
      optionsMode
    );
    setProviderKey(p);
    setModelKey(m);
    setSelectionInitialized(true);
  }, [dialogTarget, optionsMode, providerOptsQuery.data, selectionInitialized]);

  const effectiveProvider =
    providerKey.trim() || providerOptsQuery.data?.default_provider_key || '';
  const providerConfig = useMemo(
    () => (providerOptsQuery.data?.providers ?? []).find((p) => p.key === effectiveProvider),
    [providerOptsQuery.data?.providers, effectiveProvider]
  );

  const productionProvidersReady = !isProductionInventory || hasProductionProviders(providerOptsQuery.data);

  const openDialogForAisle = useCallback(
    (aisleId: string, aisleCode: string, clientSupplierId: string | null) => {
      setProcessError(null);
      setProviderKey('');
      setModelKey('');
      setSelectionInitialized(false);
      setDialogTarget({ aisleId, aisleCode, clientSupplierId });
    },
    [setProcessError]
  );

  const closeDialog = useCallback(() => {
    setDialogTarget(null);
    setSelectionInitialized(false);
  }, []);

  const handleProviderKeyChange = useCallback(
    (nextProviderKey: string) => {
      setProviderKey(nextProviderKey);
      setModelKey(modelKeyForProviderChange(nextProviderKey, providerOptsQuery.data, optionsMode));
    },
    [optionsMode, providerOptsQuery.data]
  );

  const requestProcess = useCallback(
    async (aisleId: string, aisleCode: string, clientSupplierId: string | null = null) => {
      openDialogForAisle(aisleId, aisleCode, clientSupplierId);
    },
    [openDialogForAisle]
  );

  const confirmDialog = useCallback(async () => {
    if (!dialogTarget) return;
    if (isProductionInventory && !productionProvidersReady) {
      setProcessError(t('aisle.process_no_production_providers'));
      return;
    }
    onBeforeProcessMutation?.();
    setProcessError(null);
    setProcessingAisleId(dialogTarget.aisleId);
    try {
      await processMutation.mutateAsync({
        aisleId: dialogTarget.aisleId,
        providerName: providerKey.trim() === '' ? null : providerKey.trim().toLowerCase(),
        modelName: modelKey.trim() === '' ? null : modelKey.trim(),
        promptKey: null,
      });
      showSnackbar(t('aisle.processing_started_snackbar'), 'success');
      setDialogTarget(null);
      setSelectionInitialized(false);
      onAfterSuccess?.();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setProcessError(resolveApiErrorMessage(err, 'errors.start_processing'));
    } finally {
      setProcessingAisleId(null);
    }
  }, [
    dialogTarget,
    isProductionInventory,
    modelKey,
    onAfterSuccess,
    onBeforeProcessMutation,
    processMutation,
    productionProvidersReady,
    providerKey,
    setProcessError,
    showSnackbar,
    t,
  ]);

  return {
    processingAisleId,
    processError,
    setProcessError,
    requestProcess,
    dialogTarget,
    closeDialog,
    confirmDialog,
    providerKey,
    setProviderKey: handleProviderKeyChange,
    modelKey,
    setModelKey,
    providerOptsQuery,
    providerConfig,
    processMutation,
    isProductionInventory,
    productionProvidersReady,
  };
}
