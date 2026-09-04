import { Alert, Button, CircularProgress, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BaseDialog from '../../../components/ui/BaseDialog';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import type { AisleIdentificationMode, AisleProcessingMode, ProcessingProviderOptionsResponse } from '../../../api/types';
import {
  PROCESS_AISLE_PROCESSING_MODE_OPTIONS,
  isLegacyIdentificationMode,
  processingModeUsesVision,
} from '../../processing/mappers/processingExecutionPresentation';

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
  /** Process-aisle dispatch: AUTO | CODE_SCAN_ONLY | VISION_ONLY. */
  processingMode: AisleProcessingMode;
  onProcessingModeChange: (v: AisleProcessingMode) => void;
  /** Effective identification mode from backend inheritance (informational). */
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

const PROCESSING_OPTIONS = PROCESS_AISLE_PROCESSING_MODE_OPTIONS;

export default function AisleProcessingDialog({
  open,
  aisleCode,
  clientSupplierId,
  providerKey,
  onProviderKeyChange,
  modelKey,
  onModelKeyChange,
  processingMode,
  onProcessingModeChange,
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

  const selectedMode = String(processingMode || 'AUTO').toUpperCase() as AisleProcessingMode;
  const usesVision = processingModeUsesVision(selectedMode);
  const visionOnly = selectedMode === 'VISION_ONLY';
  const providersAvailable = (providerOptsQuery.data?.providers?.length ?? 0) > 0;
  const visionUnavailable =
    visionOnly &&
    (providerOptsQuery.isError ||
      (!providerOptsQuery.isLoading && !providersAvailable) ||
      productionProvidersUnavailable);

  const showAiProviderControls = usesVision && !deferProviderModelSelects;
  const effectiveDisplayMode = String(inheritedEffectiveMode || 'CODE_SCAN');
  const showLegacyRetirementWarning = isLegacyIdentificationMode(effectiveDisplayMode);

  const sourceLabel = identificationModeSource
    ? t(`aisle.identification_source_${String(identificationModeSource).toLowerCase()}`, {
        defaultValue: String(identificationModeSource),
      })
    : t('aisle.identification_source_system_default');

  const inheritedModeLabel = t(`aisle.identification_mode_${effectiveDisplayMode.toLowerCase()}`, {
    defaultValue: effectiveDisplayMode,
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
          <Button
            variant="contained"
            onClick={onConfirm}
            disabled={confirmDisabled || visionUnavailable}
            data-testid="process-aisle-confirm"
          >
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

        <FormControl fullWidth size="small" data-testid="process-processing-mode">
          <InputLabel id="process-processing-mode-label">{t('aisle.processing_mode_label')}</InputLabel>
          <Select
            labelId="process-processing-mode-label"
            label={t('aisle.processing_mode_label')}
            value={selectedMode}
            onChange={(e) => onProcessingModeChange(String(e.target.value).toUpperCase() as AisleProcessingMode)}
          >
            {PROCESSING_OPTIONS.map((mode) => {
              const disabledVision = mode === 'VISION_ONLY' && visionUnavailable && selectedMode !== 'VISION_ONLY'
                ? !providersAvailable && !providerOptsQuery.isLoading
                : mode === 'VISION_ONLY' && !providerOptsQuery.isLoading && !providersAvailable;
              return (
                <MenuItem
                  key={mode}
                  value={mode}
                  disabled={mode === 'VISION_ONLY' && !providerOptsQuery.isLoading && !providersAvailable}
                  data-testid={`process-processing-mode-${mode.toLowerCase()}`}
                >
                  {t(`aisle.processing_mode_${mode.toLowerCase()}`)}
                  {mode === 'AUTO' ? ` (${t('aisle.processing_mode_recommended')})` : ''}
                  {mode === 'VISION_ONLY' && disabledVision
                    ? ` — ${t('aisle.processing_mode_vision_unavailable_short')}`
                    : ''}
                </MenuItem>
              );
            })}
          </Select>
        </FormControl>

        <Alert severity="info" variant="outlined" data-testid="process-processing-mode-help">
          {t(`aisle.processing_mode_${selectedMode.toLowerCase()}_help`)}
          {visionOnly ? (
            <Typography variant="body2" sx={{ mt: 1 }} data-testid="process-vision-diagnostic-note">
              {t('aisle.processing_mode_vision_only_diagnostic')}
            </Typography>
          ) : null}
        </Alert>

        {usesVision ? (
          <Alert severity="warning" variant="outlined" data-testid="process-vision-external-send">
            {t('aisle.processing_mode_vision_may_send_images')}
          </Alert>
        ) : (
          <Alert severity="success" variant="outlined" data-testid="process-no-immediate-external">
            {t('aisle.processing_mode_code_scan_only_no_ai')}
          </Alert>
        )}

        {visionUnavailable ? (
          <Alert severity="error" variant="outlined" data-testid="process-vision-provider-missing">
            {t('aisle.processing_mode_vision_provider_missing')}
          </Alert>
        ) : null}

        <Typography variant="caption" color="text.secondary" data-testid="process-identification-source">
          {t('aisle.identification_default_reference', {
            mode: inheritedModeLabel,
            source: sourceLabel,
          })}
        </Typography>

        {showLegacyRetirementWarning ? (
          <Alert severity="warning" variant="outlined" data-testid="process-legacy-retirement-warning">
            {t('aisle.identification_legacy_retirement_warning')}
          </Alert>
        ) : null}

        {showAiProviderControls ? (
          <>
            <FormControl
              fullWidth
              size="small"
              disabled={providerOptsQuery.isError || (productionMode && productionProvidersUnavailable)}
              data-testid="process-provider-select"
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
          </>
        ) : null}

        {providerOptsQuery.isError && showAiProviderControls ? (
          <Typography variant="caption" color="error">
            {resolveApiErrorMessage(providerOptsQuery.error, 'common.provider_list_error')}
          </Typography>
        ) : null}
      </Stack>
    </BaseDialog>
  );
}
