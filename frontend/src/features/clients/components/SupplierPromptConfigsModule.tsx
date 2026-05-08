import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppSnackbar } from '../../../components/ui';
import {
  useActivateSupplierPromptConfigVersion,
  useActiveSupplierPromptConfig,
  useCreateSupplierPromptConfigVersion,
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

const PROVIDER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'gemini', label: 'Gemini' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'claude', label: 'Claude' },
  { value: 'deepseek', label: 'DeepSeek' },
];

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

  const [formValues, setFormValues] = useState<SupplierPromptConfigFormValues>({
    providerName: PROVIDER_OPTIONS[0].value,
    modelName: '',
    instructionsText: '',
  });
  const [formValidationError, setFormValidationError] = useState<string | null>(null);

  const selectedProvider = formValues.providerName.trim();
  const selectedModel = normalizeModelName(formValues.modelName);

  const versionsQuery = useSupplierPromptConfigs(
    clientId,
    supplierId,
    {
      provider_name: selectedProvider,
      model_name: selectedModel,
    },
    { enabled: Boolean(open && clientId && supplierId && selectedProvider) }
  );
  const activeQuery = useActiveSupplierPromptConfig(
    clientId,
    supplierId,
    selectedProvider,
    selectedModel,
    { enabled: Boolean(open && clientId && supplierId && selectedProvider) }
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
      if (!selectedProvider) {
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
          provider_name: selectedProvider,
          model_name: selectedModel,
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
    [createMutation, formValues.instructionsText, selectedModel, selectedProvider, showSnackbar, t]
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
      modelName={formValues.modelName}
      formValues={formValues}
      onFormChange={(next) => {
        setFormValues(next);
        if (formValidationError) setFormValidationError(null);
      }}
      formValidationError={formValidationError}
      warningMessage={warningMessage}
      providerOptions={PROVIDER_OPTIONS}
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

