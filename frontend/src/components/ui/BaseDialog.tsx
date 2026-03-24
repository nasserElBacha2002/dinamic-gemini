/**
 * BaseDialog — shared shell for **simple** operational dialogs (Re diseño 3.3 §8.11: form dialogs, confirmations body).
 *
 * **Dialog family (Sprint 2.3):**
 * - **BaseDialog** — generic title + body + optional actions (compose this for feature forms).
 * - **ConfirmDialog** — composes `BaseDialog` with a fixed two-button confirmation layout (§14.5).
 * - **WizardModal** — separate: stepper + multi-step body (§8.10); does not use `BaseDialog` to avoid awkward nesting.
 */

import { useId, type ReactNode } from 'react';
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
  type DialogProps,
} from '@mui/material';
import type { SxProps, Theme } from '@mui/material/styles';

export interface BaseDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
  maxWidth?: DialogProps['maxWidth'];
  fullWidth?: boolean;
  /** When true, backdrop / escape do not call `onClose` (e.g. while parent sets `loading`). */
  disableClose?: boolean;
  /** Applied to `DialogActions` when `actions` is set (e.g. confirm dialogs need extra padding). */
  actionsSx?: SxProps<Theme>;
}

export default function BaseDialog({
  open,
  onClose,
  title,
  subtitle,
  children,
  actions,
  maxWidth = 'sm',
  fullWidth = true,
  disableClose = false,
  actionsSx,
}: BaseDialogProps) {
  const titleId = useId();

  return (
    <Dialog
      open={open}
      onClose={disableClose ? undefined : onClose}
      maxWidth={maxWidth}
      fullWidth={fullWidth}
      aria-labelledby={titleId}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      <DialogContent>
        {subtitle ? (
          <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 2 }}>
            {subtitle}
          </Typography>
        ) : null}
        {children}
      </DialogContent>
      {actions ? <DialogActions sx={actionsSx}>{actions}</DialogActions> : null}
    </Dialog>
  );
}
