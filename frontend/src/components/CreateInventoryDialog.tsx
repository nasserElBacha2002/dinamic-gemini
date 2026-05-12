import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  CircularProgress,
  FormLabel,
  MenuItem,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import type { CreateInventoryRequest, Inventory, InventoryProcessingMode } from '../api/types';
import { getVisibleErrorMessage } from '../utils/apiErrors';
import { useCreateInventoryFlow } from '../features/inventories/hooks/useCreateInventoryFlow';
import { useClients } from '../hooks/useClients';
import WizardModal from './ui/WizardModal';

export interface CreateInventoryDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (created: Inventory) => void;
  onError: (message: string | null) => void;
  /** If provided, used instead of direct createInventory (e.g. TanStack Query mutation). */
  createInventoryFn?: (body: CreateInventoryRequest) => Promise<Inventory>;
  /** When opening from client detail, preselect this client in the selector. */
  defaultClientId?: string | null;
}

export default function CreateInventoryDialog({
  open,
  onClose,
  onSuccess,
  onError,
  createInventoryFn,
  defaultClientId = null,
}: CreateInventoryDialogProps) {
  const { t } = useTranslation();
  const { submitCreateInventory, isSubmitting: submitting, clearError } = useCreateInventoryFlow({
    createInventoryFn,
  });

  const [name, setName] = useState('');
  const [nameError, setNameError] = useState('');
  const [clientError, setClientError] = useState('');
  const [processingMode, setProcessingMode] = useState<InventoryProcessingMode>('production');
  const [selectedClientId, setSelectedClientId] = useState('');
  const clientSelectorHelpId = useId();
  const {
    data: clientsData,
    isLoading: isClientsLoading,
    isError: isClientsError,
  } = useClients({ page: 1, page_size: 200 });
  const clients = clientsData?.items ?? [];

  const reset = () => {
    setName('');
    setNameError('');
    setClientError('');
    setProcessingMode('production');
    setSelectedClientId('');
  };

  useEffect(() => {
    if (!open) return;
    const trimmed = (defaultClientId ?? '').trim();
    if (trimmed) setSelectedClientId(trimmed);
    else setSelectedClientId('');
  }, [open, defaultClientId]);

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const validate = (): boolean => {
    setNameError('');
    setClientError('');
    const trimmed = (name || '').trim();
    if (!trimmed) {
      setNameError(t('dialogs.inventory.validation_name_required'));
      return false;
    }
    if (trimmed.length > 255) {
      setNameError(t('dialogs.inventory.validation_name_max'));
      return false;
    }
    if (isClientsError) {
      setClientError(t('dialogs.inventory.client_load_error'));
      return false;
    }
    if (!isClientsLoading && clients.length === 0) {
      setClientError(t('dialogs.inventory.validation_client_required_create_first'));
      return false;
    }
    if (!selectedClientId.trim()) {
      setClientError(t('dialogs.inventory.validation_client_required'));
      return false;
    }
    return true;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setNameError('');
    setClientError('');
    clearError();
    onError(null);
    try {
      const trimmed = (name || '').trim();
      const normalizedClientId = selectedClientId.trim();
      const created = await submitCreateInventory({
        name: trimmed,
        processing_mode: processingMode,
        client_id: normalizedClientId,
      } satisfies CreateInventoryRequest);
      onSuccess(created);
      handleClose();
    } catch (e) {
      const msg = getVisibleErrorMessage(e, 'inventory');
      setNameError(msg);
      onError(msg);
    }
  };

  const clientHelperText = clientError
    ? clientError
    : isClientsError
      ? t('dialogs.inventory.client_load_error')
      : clients.length === 0
        ? t('dialogs.inventory.client_empty')
        : t('dialogs.inventory.client_helper');

  const stepLabels = t('dialogs.inventory.step_labels').split('|');

  return (
    <WizardModal
      open={open}
      onClose={handleClose}
      title={t('dialogs.inventory.wizard_title')}
      stepLabels={stepLabels}
      activeStep={0}
      actions={
        <>
          <Button onClick={handleClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => void handleSubmit()}
            variant="contained"
            disabled={
              submitting ||
              isClientsLoading ||
              isClientsError ||
              clients.length === 0
            }
          >
            {submitting ? <CircularProgress size={24} /> : t('dialogs.inventory.create_inventory_action')}
          </Button>
        </>
      }
      maxWidth="sm"
      fullWidth
    >
      <Stack spacing={2}>
        <TextField
          autoFocus
          margin="dense"
          label={t('dialogs.inventory.inventory_name')}
          fullWidth
          variant="outlined"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (nameError) setNameError('');
          }}
          error={Boolean(nameError)}
          helperText={nameError}
          disabled={submitting}
          inputProps={{ maxLength: 255 }}
        />
        <TextField
          select
          label={t('dialogs.inventory.client_label')}
          value={selectedClientId}
          onChange={(e) => {
            setSelectedClientId(e.target.value);
            if (clientError) setClientError('');
          }}
          disabled={submitting || isClientsLoading}
          helperText={clientHelperText}
          error={Boolean(clientError) || isClientsError}
          FormHelperTextProps={{ id: clientSelectorHelpId }}
          inputProps={{ 'aria-describedby': clientSelectorHelpId }}
        >
          <MenuItem value="" disabled>
            {t('dialogs.inventory.client_placeholder')}
          </MenuItem>
          {clients.map((client) => (
            <MenuItem key={client.id} value={client.id}>
              {client.name}
            </MenuItem>
          ))}
        </TextField>
        <Box>
          <FormLabel component="legend">{t('dialogs.inventory.processing_mode_label')}</FormLabel>
          <ToggleButtonGroup
            exclusive
            value={processingMode}
            onChange={(_, v: InventoryProcessingMode | null) => {
              if (v != null) setProcessingMode(v);
            }}
            size="small"
            sx={{ mt: 1 }}
            disabled={submitting}
          >
            <ToggleButton value="production">{t('dialogs.inventory.processing_mode_real')}</ToggleButton>
            <ToggleButton value="test">{t('dialogs.inventory.processing_mode_test')}</ToggleButton>
          </ToggleButtonGroup>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
            {processingMode === 'production'
              ? t('dialogs.inventory.processing_mode_real_help')
              : t('dialogs.inventory.processing_mode_test_help')}
          </Typography>
        </Box>
      </Stack>
    </WizardModal>
  );
}
