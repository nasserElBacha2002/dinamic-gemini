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
import { createInventory } from '../api/client';
import type { Inventory } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';

export interface CreateInventoryDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (created: Inventory) => void;
  onError: (message: string | null) => void;
}

export default function CreateInventoryDialog({
  open,
  onClose,
  onSuccess,
  onError,
}: CreateInventoryDialogProps) {
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState('');

  const reset = () => {
    setName('');
    setValidationError('');
  };

  const handleClose = () => {
    if (!submitting) {
      reset();
      onClose();
    }
  };

  const handleSubmit = async () => {
    const trimmed = (name || '').trim();
    if (!trimmed) {
      setValidationError('Name is required');
      return;
    }
    if (trimmed.length > 255) {
      setValidationError('Name must be at most 255 characters');
      return;
    }
    setSubmitting(true);
    setValidationError('');
    onError(null);
    try {
      const created = await createInventory({ name: trimmed });
      onSuccess(created);
      handleClose();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      const msg = getApiErrorMessage(err, 'Failed to create inventory');
      setValidationError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      onError(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Create inventory</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          label="Inventory name"
          fullWidth
          variant="outlined"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={Boolean(validationError)}
          helperText={validationError}
          disabled={submitting}
          inputProps={{ maxLength: 255 }}
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
