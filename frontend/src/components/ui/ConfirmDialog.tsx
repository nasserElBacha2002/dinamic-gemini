/**
 * ConfirmDialog — Re diseño 3.3 §14.5: destructive / irreversible actions (delete, mark invalid).
 * Composes **BaseDialog** for shared layout and unique title ids; primary confirm uses `confirmColor="error"` when needed.
 *
 * **Control model:** The parent owns async work and UI state. `loading` is **externally controlled** — set it `true`
 * while `onConfirm` runs, then `false` when done. This component does not await `onConfirm`; it only fires
 * `void onConfirm()` and disables buttons when `loading` is true. `onConfirm` may be sync or async.
 */

import type { ReactNode } from 'react';
import { Button, DialogContentText } from '@mui/material';
import BaseDialog from './BaseDialog';

export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Sync or async; parent should set `loading` around awaited work if needed. */
  onConfirm: () => void | Promise<void>;
  /** When true, buttons are disabled and close-on-backdrop is blocked — set by parent during submit. */
  loading?: boolean;
  /** Label for the confirm button while `loading` is true (e.g. Working…). */
  confirmPendingLabel?: string;
  /** Use error-colored confirm for destructive flows. */
  confirmColor?: 'primary' | 'error';
}

export default function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  loading = false,
  confirmPendingLabel = 'Working…',
  confirmColor = 'primary',
}: ConfirmDialogProps) {
  return (
    <BaseDialog
      open={open}
      onClose={onClose}
      title={title}
      disableClose={loading}
      maxWidth="xs"
      fullWidth
      actionsSx={{ px: 3, pb: 2 }}
      actions={
        <>
          <Button onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant="contained"
            color={confirmColor}
            onClick={() => void onConfirm()}
            disabled={loading}
          >
            {loading ? confirmPendingLabel : confirmLabel}
          </Button>
        </>
      }
    >
      <DialogContentText component="div">{description}</DialogContentText>
    </BaseDialog>
  );
}
