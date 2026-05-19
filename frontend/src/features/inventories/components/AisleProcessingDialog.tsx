import { Alert, Button, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BaseDialog from '../../../components/ui/BaseDialog';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import type { ProcessingProviderOptionsResponse } from '../../../api/types';

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
  providerOptsQuery: ProcessingProviderOptionsQueryLike;
  providerConfig:
    | ProcessingProviderOptionsResponse['providers'][number]
    | undefined;
  /** Production inventories: one default model per provider; hide server-default empty options. */
  productionMode?: boolean;
  productionProvidersReady?: boolean;
  onClose: () => void;
  onConfirm: () => void;
  confirmDisabled: boolean;
  confirmBusyLabel: boolean;
}

export default function AisleProcessingDialog({
  open,
  aisleCode,
  clientSupplierId,
  providerKey,
  onProviderKeyChange,
  modelKey,
  onModelKeyChange,
  providerOptsQuery,
  providerConfig,
  productionMode = false,
  productionProvidersReady = true,
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
        {productionMode && !productionProvidersReady && !providerOptsQuery.isLoading ? (
          <Alert severity="warning" data-testid="process-no-production-providers">
            {t('aisle.process_no_production_providers')}
          </Alert>
        ) : null}
        <FormControl
          fullWidth
          size="small"
          disabled={
            providerOptsQuery.isLoading ||
            (productionMode && !productionProvidersReady)
          }
        >
          <InputLabel id="process-provider-label">{t('aisle.process_ai_provider')}</InputLabel>
          <Select
            labelId="process-provider-label"
            label={t('aisle.process_ai_provider')}
            value={providerKey}
            onChange={(e) => onProviderKeyChange(String(e.target.value))}
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
            providerOptsQuery.isLoading ||
            !providerConfig?.models?.length ||
            singleProductionModel
          }
        >
          <InputLabel id="process-model-label">{t('common.model')}</InputLabel>
          <Select
            labelId="process-model-label"
            label={t('common.model')}
            value={modelKey}
            onChange={(e) => onModelKeyChange(String(e.target.value))}
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

        {providerOptsQuery.isError ? (
          <Typography variant="caption" color="error">
            {resolveApiErrorMessage(providerOptsQuery.error, 'common.provider_list_error')}
          </Typography>
        ) : null}
      </Stack>
    </BaseDialog>
  );
}
