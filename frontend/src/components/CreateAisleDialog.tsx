import { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  CircularProgress,
} from '@mui/material';
import { createAisle } from '../api/client';
import type { CreateAisleRequest } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';

export interface CreateAisleDialogProps {
  open: boolean;
  inventoryId: string;
  onClose: () => void;
  onSuccess: () => void;
  /** Optional. Called with a message when the parent should show an error (e.g. global snackbar). */
  onError?: (message: string | null) => void;
  /** If provided, used instead of direct createAisle (e.g. TanStack Query mutation). */
  createAisleFn?: (body: CreateAisleRequest) => Promise<unknown>;
}

export default function CreateAisleDialog({
  open,
  inventoryId,
  onClose,
  onSuccess,
  onError,
  createAisleFn,
}: CreateAisleDialogProps) {
  const doCreate = createAisleFn ?? ((body: CreateAisleRequest) => createAisle(inventoryId, body));
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState('');

  const reset = () => {
    setCode('');
    setValidationError('');
  };

  const handleClose = () => {
    if (!submitting) {
      reset();
      onClose();
    }
  };

  const handleSubmit = async () => {
    const trimmed = (code || '').trim();
    if (!trimmed) {
      setValidationError('Code is required');
      return;
    }
    if (trimmed.length > 64) {
      setValidationError('Code must be at most 64 characters');
      return;
    }
    if (!inventoryId) {
      setValidationError('Inventory not set');
      return;
    }
    setSubmitting(true);
    setValidationError('');
    onError?.(null);
    try {
      await doCreate({ code: trimmed });
      onSuccess();
      handleClose();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      const msg = getApiErrorMessage(err, 'Failed to create aisle');
      if (err.status === 409) {
        setValidationError(
          typeof msg === 'string' ? msg : 'An aisle with this code already exists in this inventory.'
        );
      } else {
        setValidationError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }
      onError?.(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Create aisle</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          label="Aisle code"
          fullWidth
          variant="outlined"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          error={Boolean(validationError)}
          helperText={validationError}
          disabled={submitting}
          inputProps={{ maxLength: 64 }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={submitting}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} variant="contained" disabled={submitting}>
          {submitting ? <CircularProgress size={24} /> : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
