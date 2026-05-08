import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppSnackbar } from '../../../components/ui';
import {
  useActivateSupplierPromptConfigVersion,
  useActiveSupplierPromptConfig,
  useCreateSupplierPromptConfigVersion,
  useProcessingProviderOptions,
  useSupplierPromptConfigs,
} from '../../../hooks';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import SupplierPromptConfigsDrawer from './SupplierPromptConfigsDrawer';
import type { SupplierPromptConfigFormValues } from './SupplierPromptConfigForm';

export interface SupplierPromptConfigsModuleProps {
  clientId: string;
  supplierId: string;
  supplierName: string;
  open: boolean;
  onClose: () => void;
}

function normalizeModelName(value: string): string | null {
  return value.trim() || null;
}

function getWarningMessage(text: string, warningCopy: string): string | null {
  const lowered = text.toLowerCase();
  const suspicious = ['ignorar json', 'cambiar formato', 'no respetar estructura', 'devolver xml'];
  return suspicious.some((needle) => lowered.includes(needle)) ? warningCopy : null;
}

export default function SupplierPromptConfigsModule({
  clientId,
  supplierId,
  supplierName,
  open,
  onClose,
}: SupplierPromptConfigsModuleProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const processingOptionsQuery = useProcessingProviderOptions({ enabled: open });

  const providerOptions = useMemo(
    () =>
      (processingOptionsQuery.data?.providers ?? []).map((provider) => ({
        value: provider.key,
        label: provider.label || provider.key,
      })),
    [processingOptionsQuery.data?.providers]
  );

  const [formValues, setFormValues] = useState<SupplierPromptConfigFormValues>({
    scopeType: 'all_providers_models',
    providerName: '',
    modelName: '',
    instructionsText: '',
  });
  const [formValidationError, setFormValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (providerOptions.length === 0) return;
    setFormValues((prev) => {
      if (prev.providerName && providerOptions.some((provider) => provider.value === prev.providerName)) {
        return prev;
      }
      return {
        ...prev,
        providerName: providerOptions[0].value,
        modelName: prev.scopeType === 'provider_model' ? prev.modelName : '',
      };
    });
  }, [providerOptions]);

  const selectedProviderConfig = useMemo(
    () =>
      (processingOptionsQuery.data?.providers ?? []).find((provider) => provider.key === formValues.providerName),
    [formValues.providerName, processingOptionsQuery.data?.providers]
  );
  const modelOptions = useMemo(
    () => [
      {
        value: '',
        label: t('clients.suppliers.prompt_configs.default_model_label'),
      },
      ...((selectedProviderConfig?.models ?? []).map((model) => ({
        value: model.id,
        label: model.label || model.id,
      })) as Array<{ value: string; label: string }>),
    ],
    [selectedProviderConfig?.models, t]
  );

  const selectedProvider = formValues.providerName.trim();
  const selectedModel = normalizeModelName(formValues.modelName);
  const scopeQuery =
    formValues.scopeType === 'all_providers_models'
      ? { scope: 'all' as const }
      : {
          provider_name: selectedProvider,
          model_name: formValues.scopeType === 'provider_model' ? selectedModel : null,
        };

  const versionsQuery = useSupplierPromptConfigs(
    clientId,
    supplierId,
    scopeQuery,
    {
      enabled:
        Boolean(open && clientId && supplierId) &&
        (formValues.scopeType === 'all_providers_models' || Boolean(selectedProvider)),
    }
  );
  const activeQuery = useActiveSupplierPromptConfig(
    clientId,
    supplierId,
    formValues.scopeType === 'all_providers_models' ? undefined : selectedProvider,
    formValues.scopeType === 'provider_model' ? selectedModel : null,
    {
      enabled:
        Boolean(open && clientId && supplierId) &&
        (formValues.scopeType === 'all_providers_models' || Boolean(selectedProvider)),
    }
  );
  const createMutation = useCreateSupplierPromptConfigVersion(clientId, supplierId);
  const activateMutation = useActivateSupplierPromptConfigVersion(clientId, supplierId);

  const warningMessage = useMemo(
    () =>
      getWarningMessage(
        formValues.instructionsText,
        t('clients.suppliers.prompt_configs.non_blocking_format_warning')
      ),
    [formValues.instructionsText, t]
  );

  const loadingError =
    versionsQuery.isError && versionsQuery.error
      ? resolveApiErrorMessage(versionsQuery.error, 'clients.suppliers.prompt_configs.load_error')
      : null;
  const createError =
    createMutation.isError && createMutation.error
      ? resolveApiErrorMessage(createMutation.error, 'clients.suppliers.prompt_configs.create_error')
      : null;
  const activateError =
    activateMutation.isError && activateMutation.error
      ? resolveApiErrorMessage(activateMutation.error, 'clients.suppliers.prompt_configs.activate_error')
      : null;

  const handleClose = useCallback(() => {
    onClose();
    createMutation.reset();
    activateMutation.reset();
    setFormValidationError(null);
  }, [activateMutation, createMutation, onClose]);

  const handleCreateVersion = useCallback(
    (activate: boolean) => {
      const normalizedInstructions = formValues.instructionsText.trim();
      if (formValues.scopeType !== 'all_providers_models' && !selectedProvider) {
        setFormValidationError(t('clients.suppliers.prompt_configs.invalid_provider_error'));
        return;
      }
      if (!normalizedInstructions) {
        setFormValidationError(t('clients.suppliers.prompt_configs.blank_instructions_error'));
        return;
      }
      setFormValidationError(null);
      void createMutation
        .mutateAsync({
          provider_name:
            formValues.scopeType === 'all_providers_models' ? null : selectedProvider,
          model_name: formValues.scopeType === 'provider_model' ? selectedModel : null,
          instructions_text: normalizedInstructions,
          activate,
        })
        .then(() => {
          showSnackbar(
            t(
              activate
                ? 'clients.suppliers.prompt_configs.created_and_activated_success'
                : 'clients.suppliers.prompt_configs.created_success'
            ),
            'success'
          );
          setFormValues((prev) => ({
            ...prev,
            instructionsText: '',
          }));
        })
        .catch(() => {
          /* Drawer surfaces mutation error */
        });
    },
    [
      createMutation,
      formValues.instructionsText,
      formValues.scopeType,
      selectedModel,
      selectedProvider,
      showSnackbar,
      t,
    ]
  );

  const handleActivateVersion = useCallback(
    async (configId: string) => {
      try {
        await activateMutation.mutateAsync(configId);
        showSnackbar(t('clients.suppliers.prompt_configs.activated_success'), 'success');
      } catch {
        /* Drawer surfaces mutation error */
      }
    },
    [activateMutation, showSnackbar, t]
  );

  return (
    <SupplierPromptConfigsDrawer
      supplierName={supplierName}
      open={open}
      onClose={handleClose}
      providerName={selectedProvider}
      modelName={formValues.scopeType === 'provider_model' ? formValues.modelName : ''}
      scopeType={formValues.scopeType}
      formValues={formValues}
      onFormChange={(next) => {
        setFormValues(next);
        if (formValidationError) setFormValidationError(null);
      }}
      formValidationError={formValidationError}
      warningMessage={warningMessage}
      providerOptions={providerOptions}
      modelOptions={modelOptions}
      isModelOptionsLoading={processingOptionsQuery.isLoading}
      activeConfig={activeQuery.data ?? null}
      versions={versionsQuery.data?.items ?? []}
      isLoadingVersions={versionsQuery.isLoading}
      isLoadingActive={activeQuery.isLoading}
      loadingError={loadingError}
      createError={createError}
      activateError={activateError}
      isCreating={createMutation.isPending}
      isActivating={activateMutation.isPending}
      onRetry={() => {
        void versionsQuery.refetch();
        void activeQuery.refetch();
      }}
      onCreateVersion={handleCreateVersion}
      onActivateVersion={handleActivateVersion}
    />
  );
}

