import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, CircularProgress, TextField } from '@mui/material';
import type { UpdateInventoryRequest } from '../../../api/types';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import BaseDialog from '../../../components/ui/BaseDialog';

export interface EditInventoryNameDialogProps {
  open: boolean;
  currentName: string;
  onClose: () => void;
  onSuccess?: () => void;
  updateInventoryFn: (body: UpdateInventoryRequest) => Promise<unknown>;
}

function normalizeApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(String(error));
}

export default function EditInventoryNameDialog({
  open,
  currentName,
  onClose,
  onSuccess,
  updateInventoryFn,
}: EditInventoryNameDialogProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(currentName);
  const [validationError, setValidationError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const trimmed = useMemo(() => name.trim(), [name]);
  const originalTrimmed = useMemo(() => currentName.trim(), [currentName]);
  const unchanged = trimmed === originalTrimmed;
  const tooLong = trimmed.length > 255;
  const saveDisabled = isSubmitting || !trimmed || unchanged || tooLong;

  useEffect(() => {
    if (!open) return;
    setName(currentName);
    setValidationError('');
  }, [open, currentName]);

  const handleClose = () => {
    if (isSubmitting) return;
    setValidationError('');
    onClose();
  };

  const validate = (): string => {
    if (!trimmed) return t('dialogs.inventory.validation_name_required');
    if (tooLong) return t('dialogs.inventory.validation_name_max');
    return '';
  };

  const handleSubmit = async () => {
    const err = validate();
    if (err) {
      setValidationError(err);
      return;
    }
    if (unchanged) return;
    setValidationError('');
    setIsSubmitting(true);
    try {
      await updateInventoryFn({ name: trimmed });
      onSuccess?.();
      handleClose();
    } catch (e) {
      setValidationError(resolveApiErrorMessage(normalizeApiError(e), 'errors.request_failed'));
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
      title={t('inventory.edit_name_title')}
      description={t('inventory.edit_name_subtitle')}
      error={validationError || undefined}
      actions={
        <>
          <Button onClick={handleClose} disabled={isSubmitting}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleSubmit()}
            disabled={saveDisabled}
            data-testid="edit-inventory-name-save"
          >
            {isSubmitting ? <CircularProgress size={18} color="inherit" /> : t('common.save')}
          </Button>
        </>
      }
    >
      <TextField
        inputRef={inputRef}
        autoFocus
        fullWidth
        margin="dense"
        label={t('dialogs.inventory.inventory_name')}
        value={name}
        onChange={(e) => {
          setName(e.target.value);
          if (validationError) setValidationError('');
        }}
        inputProps={{ maxLength: 255, 'data-testid': 'edit-inventory-name-input' }}
        disabled={isSubmitting}
      />
    </BaseDialog>
  );
}
