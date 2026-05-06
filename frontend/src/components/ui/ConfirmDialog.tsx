/**
 * ConfirmDialog — Re diseño 3.3 §14.5: destructive / irreversible actions (delete, mark invalid).
 * Composes **BaseDialog** for shared layout and unique title ids; primary confirm uses `confirmColor="error"` when needed.
 *
 * **Control model:** The parent owns async work and UI state. `loading` is **externally controlled** — set it `true`
 * while `onConfirm` runs, then `false` when done. This component does not await `onConfirm`; it only fires
 * `void onConfirm()` and disables buttons when `loading` is true. `onConfirm` may be sync or async.
 */

import type { ReactNode } from 'react';
import { Alert, Button, DialogContentText, type DialogProps } from '@mui/material';
import { useTranslation } from 'react-i18next';
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
  /** Primary action color (default matches most confirms; `warning` for reversible-but-risky ops). */
  confirmColor?: 'primary' | 'error' | 'warning';
  /** Inline error under the description (e.g. failed destructive confirm). Cleared by parent when dialog closes. */
  errorMessage?: string | null;
  /** Dialog width; defaults to `xs` for compact confirms. */
  maxWidth?: DialogProps['maxWidth'];
}

export default function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  loading = false,
  confirmPendingLabel,
  confirmColor = 'primary',
  errorMessage,
  maxWidth = 'xs',
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const cancel = cancelLabel ?? t('common.cancel');
  const confirm = confirmLabel ?? t('common.confirm');
  const pending = confirmPendingLabel ?? t('common.working');
  return (
    <BaseDialog
      open={open}
      onClose={onClose}
      title={title}
      disableClose={loading}
      maxWidth={maxWidth}
      fullWidth
      actionsSx={{ px: 3, pb: 2 }}
      actions={
        <>
          <Button onClick={onClose} disabled={loading}>
            {cancel}
          </Button>
          <Button
            variant="contained"
            color={confirmColor}
            onClick={() => void onConfirm()}
            disabled={loading}
          >
            {loading ? pending : confirm}
          </Button>
        </>
      }
    >
      {typeof description === 'string' ? (
        <DialogContentText>{description}</DialogContentText>
      ) : (
        description
      )}
      {errorMessage ? (
        <Alert severity="error" sx={{ mt: 2 }}>
          {errorMessage}
        </Alert>
      ) : null}
    </BaseDialog>
  );
}
