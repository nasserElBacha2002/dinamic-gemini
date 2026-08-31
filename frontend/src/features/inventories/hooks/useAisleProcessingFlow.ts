import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getAisleProcessingState,
  recoverAisleProcessing,
} from '../../../api/aislesApi';
import {
  ApiError,
  type AisleIdentificationMode,
  type AisleProcessingMode,
} from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAppSnackbar } from '../../../components/ui';
import { useProcessingProviderOptions, useStartAisleProcessing } from '../../../hooks';
import {
  initialProcessingSelection,
  modelKeyForProviderChange,
  type ProcessingProviderOptionsMode,
} from '../utils/processingProviderSelection';
import { processingModeUsesVision } from '../../processing/mappers/processingExecutionPresentation';

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
  effectiveIdentificationMode?: AisleIdentificationMode | string | null;
  identificationModeSource?: string | null;
  configuredIdentificationMode?: AisleIdentificationMode | string | null;
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
  const [processingMode, setProcessingMode] = useState<AisleProcessingMode>('AUTO');
  const [selectionInitialized, setSelectionInitialized] = useState(false);

  const optionsMode: ProcessingProviderOptionsMode = isProductionInventory
    ? 'production'
    : 'test';

  const processMutation = useStartAisleProcessing(inventoryId);
  const providerOptsQuery = useProcessingProviderOptions({
    enabled: Boolean(dialogTarget && inventoryId),
    mode: optionsMode,
  });

  const productionOptionsLoading =
    isProductionInventory &&
    Boolean(dialogTarget) &&
    providerOptsQuery.isLoading;

  const productionProvidersReady =
    isProductionInventory &&
    Boolean(dialogTarget) &&
    !providerOptsQuery.isLoading &&
    !providerOptsQuery.isError &&
    (providerOptsQuery.data?.providers?.length ?? 0) > 0;

  const productionProvidersUnavailable =
    isProductionInventory &&
    Boolean(dialogTarget) &&
    !providerOptsQuery.isLoading &&
    (providerOptsQuery.isError ||
      (providerOptsQuery.data != null &&
        (providerOptsQuery.data.providers?.length ?? 0) === 0));

  useEffect(() => {
    if (!dialogTarget || selectionInitialized || !providerOptsQuery.data) {
      return;
    }
    if (isProductionInventory && (providerOptsQuery.data.providers?.length ?? 0) === 0) {
      return;
    }
    const { providerKey: p, modelKey: m } = initialProcessingSelection(
      providerOptsQuery.data,
      optionsMode
    );
    setProviderKey(p);
    setModelKey(m);
    setSelectionInitialized(true);
  }, [
    dialogTarget,
    isProductionInventory,
    optionsMode,
    providerOptsQuery.data,
    selectionInitialized,
  ]);

  const effectiveProvider =
    providerKey.trim() || providerOptsQuery.data?.default_provider_key || '';
  const providerConfig = useMemo(
    () => (providerOptsQuery.data?.providers ?? []).find((p) => p.key === effectiveProvider),
    [providerOptsQuery.data?.providers, effectiveProvider]
  );

  const openDialogForAisle = useCallback(
    (
      aisleId: string,
      aisleCode: string,
      clientSupplierId: string | null,
      identification?: {
        effectiveMode?: AisleIdentificationMode | string | null;
        source?: string | null;
        configured?: AisleIdentificationMode | string | null;
      }
    ) => {
      setProcessError(null);
      setProviderKey('');
      setModelKey('');
      setSelectionInitialized(false);
      setProcessingMode('AUTO');
      const effective =
        identification?.effectiveMode ||
        identification?.configured ||
        'CODE_SCAN';
      setDialogTarget({
        aisleId,
        aisleCode,
        clientSupplierId,
        effectiveIdentificationMode: identification?.effectiveMode ?? effective,
        identificationModeSource: identification?.source ?? null,
        configuredIdentificationMode: identification?.configured ?? null,
      });
    },
    [setProcessError]
  );

  const closeDialog = useCallback(() => {
    setDialogTarget(null);
    setSelectionInitialized(false);
    setProcessingMode('AUTO');
  }, []);

  const handleProviderKeyChange = useCallback(
    (nextProviderKey: string) => {
      setProviderKey(nextProviderKey);
      setModelKey(modelKeyForProviderChange(nextProviderKey, providerOptsQuery.data, optionsMode));
    },
    [optionsMode, providerOptsQuery.data]
  );

  const requestProcess = useCallback(
    async (
      aisleId: string,
      aisleCode: string,
      clientSupplierId: string | null = null,
      identification?: {
        effectiveMode?: AisleIdentificationMode | string | null;
        source?: string | null;
        configured?: AisleIdentificationMode | string | null;
      }
    ) => {
      openDialogForAisle(aisleId, aisleCode, clientSupplierId, identification);
    },
    [openDialogForAisle]
  );

  const confirmDialog = useCallback(async () => {
    if (!dialogTarget) return;
    if (productionProvidersUnavailable && processingModeUsesVision(processingMode)) {
      setProcessError(t('aisle.process_no_production_providers'));
      return;
    }
    if (processingMode === 'VISION_ONLY') {
      const providers = providerOptsQuery.data?.providers ?? [];
      if (providerOptsQuery.isError || providers.length === 0) {
        setProcessError(t('aisle.processing_mode_vision_provider_missing'));
        return;
      }
    }
    if (productionOptionsLoading) {
      return;
    }
    onBeforeProcessMutation?.();
    setProcessError(null);
    setProcessingAisleId(dialogTarget.aisleId);
    try {
      // Authoritative lifecycle (shared with mobile): consult processing-state before start.
      let state = await getAisleProcessingState(inventoryId, dialogTarget.aisleId);
      if (state.state === 'RECOVERY_REQUIRED' || state.state === 'SUSPECTED_STALE') {
        const recovered = await recoverAisleProcessing(inventoryId, dialogTarget.aisleId, {
          reason: 'web_client_pre_process_recover',
        });
        state = recovered.processing_state;
      }
      if (!state.can_start_new || state.state === 'STARTING' || state.state === 'RUNNING') {
        setProcessError(
          t('aisle.process_already_in_progress', {
            defaultValue: 'El pasillo ya tiene un procesamiento en curso.',
          })
        );
        return;
      }

      await processMutation.mutateAsync({
        aisleId: dialogTarget.aisleId,
        providerName: providerKey.trim() === '' ? null : providerKey.trim().toLowerCase(),
        modelName: modelKey.trim() === '' ? null : modelKey.trim(),
        promptKey: null,
        processingMode,
      });
      showSnackbar(t('aisle.processing_started_snackbar'), 'success');
      setDialogTarget(null);
      setSelectionInitialized(false);
      setProcessingMode('AUTO');
      onAfterSuccess?.();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      setProcessError(resolveApiErrorMessage(err, 'errors.start_processing'));
    } finally {
      setProcessingAisleId(null);
    }
  }, [
    dialogTarget,
    inventoryId,
    modelKey,
    onAfterSuccess,
    onBeforeProcessMutation,
    processMutation,
    processingMode,
    productionOptionsLoading,
    productionProvidersUnavailable,
    providerKey,
    providerOptsQuery.data?.providers,
    providerOptsQuery.isError,
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
    processingMode,
    setProcessingMode,
    providerOptsQuery,
    providerConfig,
    processMutation,
    isProductionInventory,
    productionOptionsLoading,
    productionProvidersReady,
    productionProvidersUnavailable,
  };
}
