import { useState } from 'react';
import { Button, CircularProgress, TextField } from '@mui/material';
import { createInventory } from '../api/client';
import type { CreateInventoryRequest, Inventory } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import BaseDialog from './ui/BaseDialog';

export interface CreateInventoryDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (created: Inventory) => void;
  onError: (message: string | null) => void;
  /** If provided, used instead of direct createInventory (e.g. TanStack Query mutation). */
  createInventoryFn?: (body: CreateInventoryRequest) => Promise<Inventory>;
}

export default function CreateInventoryDialog({
  open,
  onClose,
  onSuccess,
  onError,
  createInventoryFn,
}: CreateInventoryDialogProps) {
  const doCreate = createInventoryFn ?? createInventory;
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState('');
  const canClose = !submitting;

  const validateStep1 = (): boolean => {
    const trimmed = (name || '').trim();
    if (!trimmed) {
      setValidationError('Name is required');
      return false;
    }
    if (trimmed.length > 255) {
      setValidationError('Name must be at most 255 characters');
      return false;
    }
    return true;
  };

  const handleSubmit = async () => {
    if (!validateStep1()) return;
    setSubmitting(true);
    setValidationError('');
    onError(null);
    try {
      const trimmed = (name || '').trim();
      const created = await doCreate({ name: trimmed });
      onSuccess(created);
      setName('');
      onClose();
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e));
      const msg = getApiErrorMessage(err, 'Failed to create inventory');
      setValidationError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      onError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <BaseDialog
      open={open}
      onClose={onClose}
      title="Create inventory"
      subtitle="Create an inventory to manage aisles, processing, and review work."
      disableClose={!canClose}
      maxWidth="xs"
      actions={
        <>
          <Button onClick={onClose} disabled={!canClose}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} variant="contained" disabled={submitting}>
            {submitting ? <CircularProgress size={20} /> : 'Create inventory'}
          </Button>
        </>
      }
    >
      <TextField
        autoFocus
        margin="dense"
        label="Inventory name"
        fullWidth
        variant="outlined"
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={Boolean(validationError)}
        helperText={validationError || ' '}
        disabled={submitting}
        inputProps={{ maxLength: 255 }}
      />
    </BaseDialog>
  );
}
