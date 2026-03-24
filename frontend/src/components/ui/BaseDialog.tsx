/**
 * BaseDialog — consistent modal shell for operational dialogs (Re diseño 3.3 §8.11, form dialogs).
 * Feature dialogs (Create Aisle, etc.) can compose this for shared spacing and width.
 */

import type { ReactNode } from 'react';
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
  type DialogProps,
} from '@mui/material';

export interface BaseDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
  maxWidth?: DialogProps['maxWidth'];
  fullWidth?: boolean;
  /** When true, backdrop click and escape do not close (use during submit). */
  disableClose?: boolean;
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
}: BaseDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={disableClose ? undefined : onClose}
      maxWidth={maxWidth}
      fullWidth={fullWidth}
      aria-labelledby="base-dialog-title"
    >
      <DialogTitle id="base-dialog-title">{title}</DialogTitle>
      <DialogContent>
        {subtitle ? (
          <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 2 }}>
            {subtitle}
          </Typography>
        ) : null}
        {children}
      </DialogContent>
      {actions ? <DialogActions>{actions}</DialogActions> : null}
    </Dialog>
  );
}
