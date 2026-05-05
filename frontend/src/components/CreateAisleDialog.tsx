import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  TextField,
  CircularProgress,
} from '@mui/material';
import { createAisle } from '../api/client';
import type { CreateAisleRequest } from '../api/types';
import { ApiError } from '../api/types';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import BaseDialog from './ui/BaseDialog';

export interface CreateAisleDialogProps {
  open: boolean;
  inventoryId: string;
  onClose: () => void;
  onSuccess: () => void;
  /** Optional. Called with a message when the parent should show an error (e.g. global snackbar). */
  onError?: (message: string | null) => void;
  /** If provided, used instead of direct createAisle (e.g. TanStack Query mutation). */
  createAisleFn?: (body: CreateAisleRequest) => Promise<unknown>;
  /** Optional pre-validation: existing aisle codes in this inventory (from the current list view). */
  existingAisleCodes?: string[];
}

export default function CreateAisleDialog({
  open,
  inventoryId,
  onClose,
  onSuccess,
  onError,
  createAisleFn,
  existingAisleCodes,
}: CreateAisleDialogProps) {
  const { t } = useTranslation();
  const doCreate = createAisleFn ?? ((body: CreateAisleRequest) => createAisle(inventoryId, body));
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState('');
  const [createdCode, setCreatedCode] = useState<string | null>(null);
  const codeInputRef = useRef<HTMLInputElement>(null);

  const normalizedExistingCodes = useMemo(() => {
    const list = existingAisleCodes ?? [];
    return new Set(list.map((c) => String(c || '').trim().toLowerCase()).filter(Boolean));
  }, [existingAisleCodes]);

  const reset = () => {
    setCode('');
    setValidationError('');
    setCreatedCode(null);
  };

  useEffect(() => {
    if (!open) return;
    queueMicrotask(() => {
      reset();
      onError?.(null);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleClose = () => {
    if (!submitting) {
      reset();
      onClose();
    }
  };

  const validateForSubmit = (next: string): string => {
    const trimmed = (next || '').trim();
    if (!trimmed) return t('dialogs.aisle.validation_code_required');
    if (trimmed.length > 64) return t('dialogs.aisle.validation_code_max');
    if (!inventoryId) return t('dialogs.aisle.validation_inventory_missing');
    if (normalizedExistingCodes.has(trimmed.toLowerCase())) {
      return t('dialogs.aisle.validation_duplicate');
    }
    return '';
  };

  const validateForTyping = (next: string): string => {
    const trimmed = (next || '').trim();
    // Keep typing experience calm: don't show "required" while user is editing.
    if (!trimmed) return '';
    if (trimmed.length > 64) return t('dialogs.aisle.validation_code_max');
    if (normalizedExistingCodes.has(trimmed.toLowerCase())) {
      return t('dialogs.aisle.validation_duplicate');
    }
    return '';
  };

  const handleSubmit = async () => {
    const trimmed = (code || '').trim();
    const errMsg = validateForSubmit(trimmed);
    if (errMsg) {
      setValidationError(errMsg);
      return;
    }
    setSubmitting(true);
    setValidationError('');
    try {
      await doCreate({ code: trimmed });
      onSuccess();
      setCreatedCode(trimmed);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      const msg = resolveApiErrorMessage(err, 'errors.create_aisle');
      if (err.status === 409) {
        setValidationError(typeof msg === 'string' ? msg : t('dialogs.aisle.validation_duplicate'));
      } else {
        const inline = typeof msg === 'string' ? msg : t('errors.create_aisle');
        setValidationError(inline);
        onError?.(inline);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <BaseDialog
      open={open}
      onClose={handleClose}
      disableClose={submitting}
      title={t('aisle.create_title')}
      subtitle={t('aisle.create_subtitle')}
      actionsSx={{ px: 3, pb: 2 }}
      actions={
        createdCode ? (
          <>
            <Button
              onClick={() => {
                setCreatedCode(null);
                setCode('');
                setValidationError('');
                onError?.(null);
                requestAnimationFrame(() => {
                  codeInputRef.current?.focus();
                });
              }}
            >
              {t('dialogs.aisle.create_another')}
            </Button>
            <Button onClick={handleClose} variant="contained">
              {t('common.close')}
            </Button>
          </>
        ) : (
          <>
            <Button onClick={handleClose} disabled={submitting}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleSubmit}
              variant="contained"
              disabled={submitting}
              startIcon={submitting ? <CircularProgress size={16} /> : undefined}
            >
              {t('aisle.create')}
            </Button>
          </>
        )
      }
    >
      {createdCode ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          {t('dialogs.aisle.success_created', { code: createdCode ?? '' })}
        </Alert>
      ) : null}

      <Box>
        <TextField
          autoFocus
          margin="dense"
          label={t('aisle.code_label')}
          fullWidth
          variant="outlined"
          value={code}
          onChange={(e) => {
            const next = e.target.value;
            setCode(next);
            if (!validationError) return;
            const nextMsg = validateForTyping(next);
            setValidationError(nextMsg);
            if (!nextMsg) onError?.(null);
          }}
          error={Boolean(validationError)}
          helperText={validationError || ' '}
          disabled={submitting || Boolean(createdCode)}
          inputProps={{ maxLength: 64 }}
          inputRef={codeInputRef}
          onBlur={() => {
            if (createdCode) return;
            const msg = validateForSubmit(code);
            setValidationError(msg);
          }}
        />
      </Box>
    </BaseDialog>
  );
}
