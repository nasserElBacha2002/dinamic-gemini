import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, CircularProgress, TextField } from '@mui/material';
import type { UpdateAisleRequest } from '../../../api/types';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import BaseDialog from '../../../components/ui/BaseDialog';

export interface EditAisleCodeDialogProps {
  open: boolean;
  currentCode: string;
  /** Other aisle codes in the inventory; current aisle code should be excluded by the caller. */
  existingCodes?: string[];
  onClose: () => void;
  onSuccess?: () => void;
  updateAisleFn: (body: UpdateAisleRequest) => Promise<unknown>;
}

function normalizeApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(String(error));
}

export default function EditAisleCodeDialog({
  open,
  currentCode,
  existingCodes,
  onClose,
  onSuccess,
  updateAisleFn,
}: EditAisleCodeDialogProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState(currentCode);
  const [validationError, setValidationError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const trimmed = useMemo(() => code.trim(), [code]);
  const originalTrimmed = useMemo(() => currentCode.trim(), [currentCode]);
  const isUnchanged = trimmed === originalTrimmed;
  const tooLong = trimmed.length > 64;

  const normalizedExisting = useMemo(() => {
    const list = existingCodes ?? [];
    return new Set(list.map((c) => String(c || '').trim().toLowerCase()).filter(Boolean));
  }, [existingCodes]);

  const saveDisabled = isSubmitting || !trimmed || isUnchanged || tooLong;

  useEffect(() => {
    if (!open) return;
    setCode(currentCode);
    setValidationError('');
  }, [open, currentCode]);

  const handleClose = () => {
    if (isSubmitting) return;
    setValidationError('');
    onClose();
  };

  const validate = (): string => {
    if (!trimmed) return t('dialogs.aisle.validation_code_required');
    if (tooLong) return t('dialogs.aisle.validation_code_max');
    if (normalizedExisting.has(trimmed.toLowerCase())) {
      return t('dialogs.aisle.validation_duplicate');
    }
    return '';
  };

  const handleSubmit = async () => {
    const err = validate();
    if (err) {
      setValidationError(err);
      return;
    }
    if (isUnchanged) return;
    setValidationError('');
    setIsSubmitting(true);
    try {
      await updateAisleFn({ code: trimmed });
      onSuccess?.();
      handleClose();
    } catch (e) {
      setValidationError(
        resolveApiErrorMessage(normalizeApiError(e), 'errors.aisle_duplicate_code')
      );
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
      title={t('aisle.edit_name_title')}
      description={t('aisle.edit_name_subtitle')}
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
            data-testid="edit-aisle-code-save"
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
        label={t('aisle.code_label')}
        value={code}
        onChange={(e) => {
          setCode(e.target.value);
          if (validationError) setValidationError('');
        }}
        inputProps={{ maxLength: 64, 'data-testid': 'edit-aisle-code-input' }}
        disabled={isSubmitting}
      />
    </BaseDialog>
  );
}
