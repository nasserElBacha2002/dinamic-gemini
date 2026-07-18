import { Alert, Button, CircularProgress, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BaseDialog from '../../../components/ui/BaseDialog';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import type { AisleIdentificationMode, ProcessingProviderOptionsResponse } from '../../../api/types';
import { INHERITED_IDENTIFICATION_MODE } from '../hooks/useAisleProcessingFlow';

/** Narrow query surface for the dialog — avoids coupling to full react-query generics. */
export interface ProcessingProviderOptionsQueryLike {
  data: ProcessingProviderOptionsResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

export interface AisleProcessingDialogProps {
  open: boolean;
  aisleCode: string | null;
  /** When set, the aisle is linked to a client supplier (supplier-aware prompts may apply). */
  clientSupplierId: string | null;
  providerKey: string;
  onProviderKeyChange: (v: string) => void;
  modelKey: string;
  onModelKeyChange: (v: string) => void;
  /** Select value: inherited sentinel or an explicit mode. */
  identificationMode: AisleIdentificationMode | string;
  onIdentificationModeChange: (v: AisleIdentificationMode | string) => void;
  /** Effective mode from backend inheritance. */
  inheritedEffectiveMode?: AisleIdentificationMode | string | null;
  identificationModeSource?: string | null;
  providerOptsQuery: ProcessingProviderOptionsQueryLike;
  providerConfig:
    | ProcessingProviderOptionsResponse['providers'][number]
    | undefined;
  /** Production inventories: one default model per provider; hide server-default empty options. */
  productionMode?: boolean;
  productionOptionsLoading?: boolean;
  productionProvidersReady?: boolean;
  productionProvidersUnavailable?: boolean;
  onClose: () => void;
  onConfirm: () => void;
  confirmDisabled: boolean;
  confirmBusyLabel: boolean;
}

const IDENTIFICATION_OPTIONS: AisleIdentificationMode[] = [
  'CODE_SCAN',
  'INTERNAL_OCR',
  'LEGACY_LLM',
];

export default function AisleProcessingDialog({
  open,
  aisleCode,
  clientSupplierId,
  providerKey,
  onProviderKeyChange,
  modelKey,
  onModelKeyChange,
  identificationMode,
  onIdentificationModeChange,
  inheritedEffectiveMode,
  identificationModeSource,
  providerOptsQuery,
  providerConfig,
  productionMode = false,
  productionOptionsLoading = false,
  productionProvidersReady = true,
  productionProvidersUnavailable = false,
  onClose,
  onConfirm,
  confirmDisabled,
  confirmBusyLabel,
}: AisleProcessingDialogProps) {
  const { t } = useTranslation();
  const showServerDefaultProvider = !productionMode;
  const showServerDefaultModel = !productionMode;
  const singleProductionModel =
    productionMode && (providerConfig?.models?.length ?? 0) === 1;
  const deferProviderModelSelects =
    productionMode && (productionOptionsLoading || !productionProvidersReady);

  const providerSelectValue =
    productionMode && productionOptionsLoading
      ? '__loading__'
      : providerKey || (productionMode && productionProvidersReady ? providerConfig?.key ?? '' : '');

  const modelSelectValue =
    productionMode && productionOptionsLoading
      ? '__loading__'
      : modelKey || (productionMode && productionProvidersReady ? providerConfig?.default_model ?? '' : '');

  const usingInherited = identificationMode === INHERITED_IDENTIFICATION_MODE;
  const effectiveDisplayMode = String(inheritedEffectiveMode || 'LEGACY_LLM');
  const selectedExplicitMode = usingInherited ? effectiveDisplayMode : String(identificationMode);
  const showPhase1Warning =
    selectedExplicitMode === 'CODE_SCAN' || selectedExplicitMode === 'INTERNAL_OCR';

  const sourceLabel = identificationModeSource
    ? t(`aisle.identification_source_${String(identificationModeSource).toLowerCase()}`, {
        defaultValue: String(identificationModeSource),
      })
    : t('aisle.identification_source_system_default');

  const inheritedOptionLabel = t('aisle.identification_use_inherited', {
    mode: effectiveDisplayMode,
    source: sourceLabel,
  });

  return (
    <BaseDialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      contentDividers
      title={
        aisleCode
          ? t('aisle.process_dialog_title_with_aisle', { code: aisleCode })
          : t('aisle.process_dialog_title')
      }
      actions={
        <>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button variant="contained" onClick={onConfirm} disabled={confirmDisabled}>
            {confirmBusyLabel ? t('common.starting') : t('aisle.process_start')}
          </Button>
        </>
      }
    >
      <Stack spacing={2}>
        <Typography variant="body2" color="text.secondary">
          {productionMode ? t('aisle.process_dialog_help_production') : t('aisle.process_dialog_help')}
        </Typography>
        {productionMode && productionOptionsLoading ? (
          <Stack direction="row" spacing={1} alignItems="center" data-testid="process-production-options-loading">
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">
              {t('common.loading')}
            </Typography>
          </Stack>
        ) : null}
        {productionMode && productionProvidersUnavailable ? (
          <Alert severity="warning" data-testid="process-no-production-providers">
            {t('aisle.process_no_production_providers')}
          </Alert>
        ) : null}

        <FormControl fullWidth size="small" data-testid="process-identification-mode">
          <InputLabel id="process-identification-label">{t('aisle.identification_mode_label')}</InputLabel>
          <Select
            labelId="process-identification-label"
            label={t('aisle.identification_mode_label')}
            value={identificationMode || INHERITED_IDENTIFICATION_MODE}
            onChange={(e) => onIdentificationModeChange(String(e.target.value))}
          >
            <MenuItem value={INHERITED_IDENTIFICATION_MODE} data-testid="process-identification-inherited-option">
              {inheritedOptionLabel}
            </MenuItem>
            {IDENTIFICATION_OPTIONS.map((mode) => (
              <MenuItem key={mode} value={mode}>
                {t(`aisle.identification_mode_${mode.toLowerCase()}`)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary" data-testid="process-identification-help">
          {usingInherited
            ? t('aisle.identification_will_use_inherited', {
                mode: effectiveDisplayMode,
                source: sourceLabel,
              })
            : t('aisle.identification_override_only_this_run')}
        </Typography>
        {!usingInherited ? (
          <Typography variant="caption" color="text.secondary" data-testid="process-identification-source">
            {t('aisle.identification_source_request_label')}
          </Typography>
        ) : (
          <Typography variant="caption" color="text.secondary" data-testid="process-identification-source">
            {t('aisle.identification_inherited_reference', {
              mode: effectiveDisplayMode,
              source: sourceLabel,
            })}
          </Typography>
        )}
        {showPhase1Warning ? (
          <Alert severity="info" variant="outlined" data-testid="process-identification-phase1-warning">
            {t('aisle.identification_phase1_warning')}
          </Alert>
        ) : null}

        {!deferProviderModelSelects ? (
          <>
            <FormControl
              fullWidth
              size="small"
              disabled={providerOptsQuery.isError || (productionMode && productionProvidersUnavailable)}
            >
              <InputLabel id="process-provider-label">{t('aisle.process_ai_provider')}</InputLabel>
              <Select
                labelId="process-provider-label"
                label={t('aisle.process_ai_provider')}
                value={providerSelectValue}
                onChange={(e) => {
                  const v = String(e.target.value);
                  if (v !== '__loading__') {
                    onProviderKeyChange(v);
                  }
                }}
              >
                {showServerDefaultProvider ? (
                  <MenuItem value="">
                    <em>{t('aisle.process_default_server')}</em>
                  </MenuItem>
                ) : null}
                {(providerOptsQuery.data?.providers ?? []).map((p) => (
                  <MenuItem key={p.key} value={p.key}>
                    {p.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl
              fullWidth
              size="small"
              disabled={
                providerOptsQuery.isError ||
                !providerConfig?.models?.length ||
                singleProductionModel ||
                (productionMode && productionProvidersUnavailable)
              }
            >
              <InputLabel id="process-model-label">{t('common.model')}</InputLabel>
              <Select
                labelId="process-model-label"
                label={t('common.model')}
                value={modelSelectValue}
                onChange={(e) => {
                  const v = String(e.target.value);
                  if (v !== '__loading__') {
                    onModelKeyChange(v);
                  }
                }}
              >
                {showServerDefaultModel ? (
                  <MenuItem value="">
                    <em>
                      {t('aisle.process_default_model_em', {
                        model:
                          providerConfig?.default_model ??
                          providerOptsQuery.data?.providers?.find(
                            (p) => p.key === (providerOptsQuery.data?.default_provider_key ?? '')
                          )?.default_model ??
                          '…',
                      })}
                    </em>
                  </MenuItem>
                ) : null}
                {(providerConfig?.models ?? []).map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    {m.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </>
        ) : null}

        <Alert severity="info" variant="outlined">
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            {t('aisle.process_prompt_used_heading')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('aisle.process_prompt_auto_body')}
          </Typography>
          {clientSupplierId ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {t('aisle.process_prompt_supplier_linked')}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {t('aisle.process_prompt_no_supplier')}
            </Typography>
          )}
        </Alert>

        {providerOptsQuery.isError ? (
          <Typography variant="caption" color="error">
            {resolveApiErrorMessage(providerOptsQuery.error, 'common.provider_list_error')}
          </Typography>
        ) : null}
      </Stack>
    </BaseDialog>
  );
}
