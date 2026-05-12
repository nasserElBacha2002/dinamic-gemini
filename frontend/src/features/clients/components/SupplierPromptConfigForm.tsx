import { Alert, Box, Button, FormControl, InputLabel, MenuItem, Select, Stack, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

export type SupplierPromptScopeType = 'all_providers_models' | 'provider' | 'provider_model';

export interface SupplierPromptConfigFormValues {
  scopeType: SupplierPromptScopeType;
  providerName: string;
  modelName: string;
  instructionsText: string;
}

interface SupplierPromptConfigFormProps {
  values: SupplierPromptConfigFormValues;
  onChange: (next: SupplierPromptConfigFormValues) => void;
  onSubmit: (activate: boolean) => void;
  isSubmitting?: boolean;
  errorMessage?: string | null;
  warningMessage?: string | null;
  providerOptions: Array<{ value: string; label: string }>;
  modelOptions: Array<{ value: string; label: string }>;
  isModelOptionsLoading?: boolean;
  validationError?: string | null;
}

export default function SupplierPromptConfigForm({
  values,
  onChange,
  onSubmit,
  isSubmitting = false,
  errorMessage,
  warningMessage,
  providerOptions,
  modelOptions,
  isModelOptionsLoading = false,
  validationError,
}: SupplierPromptConfigFormProps) {
  const { t } = useTranslation();

  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2">{t('clients.suppliers.prompt_configs.new_version')}</Typography>
      <FormControl size="small" fullWidth disabled={isSubmitting}>
        <InputLabel id="supplier-prompt-scope-label">
          {t('clients.suppliers.prompt_configs.scope_label')}
        </InputLabel>
        <Select
          labelId="supplier-prompt-scope-label"
          value={values.scopeType}
          label={t('clients.suppliers.prompt_configs.scope_label')}
          onChange={(event) => {
            const scopeType = String(event.target.value) as SupplierPromptScopeType;
            onChange({
              ...values,
              scopeType,
              providerName: scopeType === 'all_providers_models' ? '' : values.providerName,
              modelName: '',
            });
          }}
        >
          <MenuItem value="all_providers_models">
            {t('clients.suppliers.prompt_configs.scope_all_providers_models')}
          </MenuItem>
          <MenuItem value="provider">
            {t('clients.suppliers.prompt_configs.scope_provider')}
          </MenuItem>
          <MenuItem value="provider_model">
            {t('clients.suppliers.prompt_configs.scope_provider_model')}
          </MenuItem>
        </Select>
      </FormControl>

      {values.scopeType === 'all_providers_models' ? (
        <Typography variant="body2" color="text.secondary">
          {t('clients.suppliers.prompt_configs.scope_all_description')}
        </Typography>
      ) : null}

      {values.scopeType !== 'all_providers_models' ? (
      <FormControl size="small" fullWidth disabled={isSubmitting}>
        <InputLabel id="supplier-prompt-provider-label">
          {t('clients.suppliers.prompt_configs.provider_label')}
        </InputLabel>
        <Select
          labelId="supplier-prompt-provider-label"
          value={values.providerName}
          label={t('clients.suppliers.prompt_configs.provider_label')}
          onChange={(event) =>
            onChange({
              ...values,
              providerName: String(event.target.value),
              modelName: '',
            })
          }
        >
          {providerOptions.map((provider) => (
            <MenuItem key={provider.value} value={provider.value}>
              {provider.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      ) : null}

      {values.scopeType === 'provider_model' ? (
      <FormControl size="small" fullWidth disabled={isSubmitting || isModelOptionsLoading}>
        <InputLabel id="supplier-prompt-model-label">
          {t('clients.suppliers.prompt_configs.model_label')}
        </InputLabel>
        <Select
          labelId="supplier-prompt-model-label"
          value={values.modelName}
          label={t('clients.suppliers.prompt_configs.model_label')}
          onChange={(event) =>
            onChange({
              ...values,
              modelName: String(event.target.value),
            })
          }
        >
          {modelOptions.map((model) => (
            <MenuItem key={model.value || 'default-provider-model'} value={model.value}>
              {model.label}
            </MenuItem>
          ))}
        </Select>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
          {isModelOptionsLoading
            ? t('clients.suppliers.prompt_configs.models_loading')
            : t('clients.suppliers.prompt_configs.model_helper')}
        </Typography>
      </FormControl>
      ) : null}

      <TextField
        label={t('clients.suppliers.prompt_configs.instructions_label')}
        value={values.instructionsText}
        onChange={(event) =>
          onChange({
            ...values,
            instructionsText: event.target.value,
          })
        }
        disabled={isSubmitting}
        multiline
        minRows={6}
        fullWidth
        error={Boolean(validationError)}
        helperText={validationError || ' '}
      />

      {warningMessage ? (
        <Alert severity="warning">{warningMessage}</Alert>
      ) : null}
      {errorMessage ? (
        <Alert severity="error">{errorMessage}</Alert>
      ) : null}

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Button
          variant="contained"
          disabled={isSubmitting}
          onClick={() => onSubmit(true)}
        >
          {t('clients.suppliers.prompt_configs.save_and_activate')}
        </Button>
        <Button
          variant="outlined"
          disabled={isSubmitting}
          onClick={() => onSubmit(false)}
        >
          {t('clients.suppliers.prompt_configs.save_without_activating')}
        </Button>
      </Box>
    </Stack>
  );
}

