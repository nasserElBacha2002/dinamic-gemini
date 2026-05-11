import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAppSnackbar } from '../../../components/ui';
import { useProcessingProviderOptions, useStartAisleProcessing } from '../../../hooks';

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
  const [promptKey, setPromptKey] = useState('');

  const processMutation = useStartAisleProcessing(inventoryId);
  const providerOptsQuery = useProcessingProviderOptions({
    enabled: Boolean(dialogTarget && inventoryId),
  });

  const effectiveProvider =
    providerKey.trim() || providerOptsQuery.data?.default_provider_key || '';
  const providerConfig = useMemo(
    () => (providerOptsQuery.data?.providers ?? []).find((p) => p.key === effectiveProvider),
    [providerOptsQuery.data?.providers, effectiveProvider]
  );

  const openDialogForAisle = useCallback(
    (aisleId: string, aisleCode: string, clientSupplierId: string | null) => {
      setProcessError(null);
      setProviderKey('');
      setModelKey('');
      setPromptKey('');
      setDialogTarget({ aisleId, aisleCode, clientSupplierId });
    },
    [setProcessError]
  );

  const closeDialog = useCallback(() => {
    setDialogTarget(null);
  }, []);

  const handleProviderKeyChange = useCallback((nextProviderKey: string) => {
    setProviderKey(nextProviderKey);
    setModelKey('');
  }, []);

  const startProductionProcess = useCallback(
    async (aisleId: string) => {
      onBeforeProcessMutation?.();
      setProcessError(null);
      setProcessingAisleId(aisleId);
      try {
        await processMutation.mutateAsync({
          aisleId,
          providerName: null,
          modelName: null,
          promptKey: null,
        });
        showSnackbar(t('aisle.processing_started_snackbar'), 'success');
        onAfterSuccess?.();
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(String(e));
        setProcessError(resolveApiErrorMessage(err, 'errors.start_processing'));
      } finally {
        setProcessingAisleId(null);
      }
    },
    [onAfterSuccess, onBeforeProcessMutation, processMutation, setProcessError, showSnackbar, t]
  );

  const requestProcess = useCallback(
    async (aisleId: string, aisleCode: string, clientSupplierId: string | null = null) => {
      if (isProductionInventory) {
        await startProductionProcess(aisleId);
        return;
      }
      openDialogForAisle(aisleId, aisleCode, clientSupplierId);
    },
    [isProductionInventory, openDialogForAisle, startProductionProcess]
  );

  const confirmDialog = useCallback(async () => {
    if (!dialogTarget) return;
    onBeforeProcessMutation?.();
    setProcessError(null);
    setProcessingAisleId(dialogTarget.aisleId);
    try {
      await processMutation.mutateAsync({
        aisleId: dialogTarget.aisleId,
        providerName: providerKey.trim() === '' ? null : providerKey.trim().toLowerCase(),
        modelName: modelKey.trim() === '' ? null : modelKey.trim(),
        promptKey: promptKey.trim() === '' ? null : promptKey.trim(),
      });
      showSnackbar(t('aisle.processing_started_snackbar'), 'success');
      setDialogTarget(null);
      onAfterSuccess?.();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setProcessError(resolveApiErrorMessage(err, 'errors.start_processing'));
    } finally {
      setProcessingAisleId(null);
    }
  }, [
    dialogTarget,
    modelKey,
    onAfterSuccess,
    onBeforeProcessMutation,
    processMutation,
    promptKey,
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
    promptKey,
    setPromptKey,
    providerOptsQuery,
    providerConfig,
    processMutation,
  };
}
