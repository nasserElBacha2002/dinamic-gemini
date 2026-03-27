import { useEffect, useMemo, useRef, useState } from 'react';
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
import { getApiErrorMessage } from '../utils/apiErrors';
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
    reset();
    onError?.(null);
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
    if (!trimmed) return 'Aisle code is required.';
    if (trimmed.length > 64) return 'Aisle code must be at most 64 characters.';
    if (!inventoryId) return 'Inventory not set.';
    if (normalizedExistingCodes.has(trimmed.toLowerCase())) {
      return 'This aisle code already exists in this inventory.';
    }
    return '';
  };

  const validateForTyping = (next: string): string => {
    const trimmed = (next || '').trim();
    // Keep typing experience calm: don't show "required" while user is editing.
    if (!trimmed) return '';
    if (trimmed.length > 64) return 'Aisle code must be at most 64 characters.';
    if (normalizedExistingCodes.has(trimmed.toLowerCase())) {
      return 'This aisle code already exists in this inventory.';
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
      const msg = getApiErrorMessage(err, 'Failed to create aisle');
      if (err.status === 409) {
        setValidationError(
          typeof msg === 'string' ? msg : 'This aisle code already exists in this inventory.'
        );
      } else {
        const inline = typeof msg === 'string' ? msg : 'Failed to create aisle.';
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
      title="Create aisle"
      subtitle="Enter a short, unique aisle code for this inventory (e.g. A-01)."
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
              Create another
            </Button>
            <Button onClick={handleClose} variant="contained">
              Close
            </Button>
          </>
        ) : (
          <>
            <Button onClick={handleClose} disabled={submitting}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              variant="contained"
              disabled={submitting}
              startIcon={submitting ? <CircularProgress size={16} /> : undefined}
            >
              Create aisle
            </Button>
          </>
        )
      }
    >
      {createdCode ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          Aisle <strong>{createdCode}</strong> created.
        </Alert>
      ) : null}

      <Box>
        <TextField
          autoFocus
          margin="dense"
          label="Aisle code"
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
