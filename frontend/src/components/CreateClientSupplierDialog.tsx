import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, CircularProgress, TextField } from '@mui/material';
import type { CreateClientSupplierRequest } from '../api/types';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import BaseDialog from './ui/BaseDialog';

export interface CreateClientSupplierDialogProps {
  open: boolean;
  clientId: string;
  onClose: () => void;
  onSuccess: () => void;
  onError?: (message: string | null) => void;
  createClientSupplierFn: (body: CreateClientSupplierRequest) => Promise<unknown>;
}

function normalizeApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(String(error));
}

export default function CreateClientSupplierDialog({
  open,
  clientId,
  onClose,
  onSuccess,
  onError,
  createClientSupplierFn,
}: CreateClientSupplierDialogProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [validationError, setValidationError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const safeClientId = clientId.trim();
  const trimmedName = useMemo(() => name.trim(), [name]);

  const reset = () => {
    setName('');
    setValidationError('');
  };

  const handleClose = () => {
    if (isSubmitting) return;
    reset();
    onClose();
  };

  const validateForSubmit = (nextName: string): string => {
    if (!safeClientId) return t('clients.suppliers.dialogs.create.validation_client_required');
    if (!nextName.trim()) return t('clients.suppliers.dialogs.create.validation_name_required');
    if (nextName.trim().length > 255) return t('clients.suppliers.dialogs.create.validation_name_max');
    return '';
  };

  const handleSubmit = async () => {
    const err = validateForSubmit(name);
    if (err) {
      setValidationError(err);
      return;
    }
    setValidationError('');
    onError?.(null);
    setIsSubmitting(true);
    try {
      await createClientSupplierFn({ name: trimmedName });
      onSuccess();
      handleClose();
    } catch (e) {
      const message = resolveApiErrorMessage(
        normalizeApiError(e),
        'clients.suppliers.dialogs.create.error'
      );
      setValidationError(message);
      onError?.(message);
      requestAnimationFrame(() => inputRef.current?.focus());
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <BaseDialog
      open={open}
      onClose={handleClose}
      disableClose={isSubmitting}
      title={t('clients.suppliers.dialogs.create.title')}
      subtitle={t('clients.suppliers.dialogs.create.subtitle')}
      actions={
        <>
          <Button onClick={handleClose} disabled={isSubmitting}>
            {t('clients.suppliers.dialogs.create.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={isSubmitting}
            startIcon={isSubmitting ? <CircularProgress size={16} /> : undefined}
          >
            {isSubmitting
              ? t('clients.suppliers.dialogs.create.submitting')
              : t('clients.suppliers.dialogs.create.submit')}
          </Button>
        </>
      }
    >
      <TextField
        autoFocus
        margin="dense"
        label={t('clients.suppliers.dialogs.create.name_label')}
        placeholder={t('clients.suppliers.dialogs.create.name_placeholder')}
        fullWidth
        variant="outlined"
        value={name}
        onChange={(e) => {
          const next = e.target.value;
          setName(next);
          if (!validationError) return;
          setValidationError(validateForSubmit(next));
        }}
        error={Boolean(validationError)}
        helperText={validationError || ' '}
        disabled={isSubmitting}
        inputRef={inputRef}
        inputProps={{ maxLength: 255 }}
      />
    </BaseDialog>
  );
}
