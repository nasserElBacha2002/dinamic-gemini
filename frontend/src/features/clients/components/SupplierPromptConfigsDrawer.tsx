import { Alert, Box, Chip, Divider, Drawer, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { SupplierPromptConfig } from '../../../api/types';
import { DrawerHeader, ErrorAlert, LoadingBlock } from '../../../components/ui';
import { formatDate } from '../../../utils/formatDate';
import SupplierPromptConfigForm, {
  type SupplierPromptConfigFormValues,
  type SupplierPromptScopeType,
} from './SupplierPromptConfigForm';
import SupplierPromptConfigVersionList from './SupplierPromptConfigVersionList';

interface SupplierPromptConfigsDrawerProps {
  supplierName: string;
  open: boolean;
  /** When true, render as an in-page panel (no right Drawer shell). */
  embedded?: boolean;
  onClose: () => void;
  scopeType: SupplierPromptScopeType;
  providerName: string;
  modelName: string;
  formValues: SupplierPromptConfigFormValues;
  formValidationError?: string | null;
  warningMessage?: string | null;
  providerOptions: Array<{ value: string; label: string }>;
  modelOptions: Array<{ value: string; label: string }>;
  isModelOptionsLoading?: boolean;
  activeConfig?: SupplierPromptConfig | null;
  versions: SupplierPromptConfig[];
  isLoadingVersions: boolean;
  isLoadingActive: boolean;
  loadingError?: string | null;
  createError?: string | null;
  activateError?: string | null;
  isCreating?: boolean;
  isActivating?: boolean;
  onRetry: () => void;
  onFormChange: (next: SupplierPromptConfigFormValues) => void;
  onCreateVersion: (activate: boolean) => void;
  onActivateVersion: (configId: string) => Promise<void>;
}

function modelLabel(modelName: string | null | undefined, fallback: string): string {
  return (modelName ?? '').trim() || fallback;
}

function providerLabel(providerName: string | null | undefined, fallback: string): string {
  return (providerName ?? '').trim() || fallback;
}

export default function SupplierPromptConfigsDrawer({
  supplierName,
  open,
  embedded = false,
  onClose,
  scopeType,
  providerName,
  modelName,
  formValues,
  formValidationError,
  warningMessage,
  providerOptions,
  modelOptions,
  isModelOptionsLoading = false,
  activeConfig,
  versions,
  isLoadingVersions,
  isLoadingActive,
  loadingError,
  createError,
  activateError,
  isCreating = false,
  isActivating = false,
  onRetry,
  onFormChange,
  onCreateVersion,
  onActivateVersion,
}: SupplierPromptConfigsDrawerProps) {
  const { t } = useTranslation();
  const defaultModelLabel = t('clients.suppliers.prompt_configs.default_model_label');
  const allProvidersLabel = t('clients.suppliers.prompt_configs.all_providers_label');
  const selectedScopeLabel =
    scopeType === 'all_providers_models'
      ? `${allProvidersLabel} · ${defaultModelLabel}`
      : `${providerName} · ${modelLabel(modelName, defaultModelLabel)}`;

  const headerBlock = embedded ? (
    <Box sx={{ px: 2.5, pt: 2, pb: 1.5, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
      <Typography variant="caption" color="text.secondary">
        {supplierName}
      </Typography>
      <Typography variant="h6" sx={{ mt: 0.5 }}>
        {t('clients.suppliers.prompt_configs.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {t('clients.suppliers.prompt_configs.description')}
      </Typography>
    </Box>
  ) : (
    <DrawerHeader
      overline={
        <Typography variant="caption" color="text.secondary">
          {supplierName}
        </Typography>
      }
      title={<Typography variant="h6">{t('clients.suppliers.prompt_configs.title')}</Typography>}
      subtitle={
        <Typography variant="body2" color="text.secondary">
          {t('clients.suppliers.prompt_configs.description')}
        </Typography>
      }
      onClose={onClose}
      closeLabel={t('common.close')}
    />
  );

  const body = (
    <>
      {headerBlock}
      <Stack spacing={2} sx={{ p: 2.5, overflow: 'auto', flex: embedded ? 1 : undefined, minHeight: 0 }}>
        <Alert severity="info">{t('clients.suppliers.prompt_configs.protected_boundary_warning')}</Alert>

        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' } }}>
          <SupplierPromptConfigForm
            values={formValues}
            onChange={onFormChange}
            onSubmit={onCreateVersion}
            providerOptions={providerOptions}
            modelOptions={modelOptions}
            isModelOptionsLoading={isModelOptionsLoading}
            warningMessage={warningMessage}
            validationError={formValidationError}
            errorMessage={createError}
            isSubmitting={isCreating}
          />
          <Stack spacing={1.5}>
            <Typography variant="subtitle2">{t('clients.suppliers.prompt_configs.scope_title')}</Typography>
            <Chip label={selectedScopeLabel} variant="outlined" />
            <Typography variant="body2" color="text.secondary">
              {t('clients.suppliers.prompt_configs.scope_hint')}
            </Typography>
          </Stack>
        </Box>

        <Divider />

        <Stack spacing={1}>
          <Typography variant="subtitle1">{t('clients.suppliers.prompt_configs.active_version')}</Typography>
          {isLoadingActive ? (
            <LoadingBlock message={t('common.loading')} py={1} sx={{ justifyContent: 'flex-start' }} />
          ) : activeConfig ? (
            <Box sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: 'divider' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
                <Typography variant="subtitle2">
                  {t('clients.suppliers.prompt_configs.version_label', { version: activeConfig.version })}
                </Typography>
                <Chip
                  size="small"
                  color="success"
                  label={t('clients.suppliers.prompt_configs.active_badge')}
                />
              </Box>
              <Typography variant="caption" color="text.secondary">
                {providerLabel(activeConfig.provider_name, allProvidersLabel)} ·{' '}
                {modelLabel(activeConfig.model_name, defaultModelLabel)} ·{' '}
                {formatDate(activeConfig.updated_at)}
              </Typography>
              <Typography variant="body2" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
                {activeConfig.instructions_text}
              </Typography>
            </Box>
          ) : (
            <Box sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: 'divider' }}>
              <Typography variant="subtitle2">
                {t('clients.suppliers.prompt_configs.no_active_title')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('clients.suppliers.prompt_configs.no_active_description')}
              </Typography>
            </Box>
          )}
        </Stack>

        <Divider />

        <Stack spacing={1}>
          <Typography variant="subtitle1">{t('clients.suppliers.prompt_configs.version_history')}</Typography>
          {loadingError ? (
            <ErrorAlert message={loadingError} onRetry={onRetry} retryLabel={t('common.retry')} />
          ) : isLoadingVersions ? (
            <LoadingBlock message={t('common.loading')} py={1} sx={{ justifyContent: 'flex-start' }} />
          ) : (
            <SupplierPromptConfigVersionList
              items={versions}
              onActivate={onActivateVersion}
              isActivating={isActivating}
            />
          )}
          {activateError ? <Alert severity="error">{activateError}</Alert> : null}
        </Stack>
      </Stack>
    </>
  );

  if (embedded) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          bgcolor: 'background.paper',
        }}
      >
        {body}
      </Box>
    );
  }

  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 620 } } }}>
      {body}
    </Drawer>
  );
}

