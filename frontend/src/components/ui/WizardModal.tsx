/**
 * WizardModal — Re diseño 3.3 §8.10: guided multi-step flows (e.g. Create Inventory).
 * **Does not compose BaseDialog:** the stepper + single scrolling content region is a different layout than the
 * simple title/body/actions stack; keeping a dedicated `Dialog` here avoids forcing `BaseDialog` to support
 * stepper-specific structure.
 */

import { useId, type ReactNode } from 'react';
import { Box, Dialog, DialogActions, DialogContent, DialogTitle, Step, StepLabel, Stepper, Typography } from '@mui/material';
import type { DialogProps } from '@mui/material';
import { useAppBreakpoint } from '../../hooks/useAppBreakpoint';
import { SAFE_AREA } from '../shell/layoutConstants';

export interface WizardModalProps {
  open: boolean;
  onClose: () => void;
  /** Wizard title (e.g. "Create inventory"). */
  title: string;
  /** Step labels shown in the stepper (order matches activeStep). */
  stepLabels: readonly string[];
  activeStep: number;
  /** Content for the current step only. */
  children: ReactNode;
  /** Typically Back / Continue / Create + Cancel — full control for feature logic. */
  actions: ReactNode;
  maxWidth?: DialogProps['maxWidth'];
  fullWidth?: boolean;
}

export default function WizardModal({
  open,
  onClose,
  title,
  stepLabels,
  activeStep,
  children,
  actions,
  maxWidth = 'sm',
  fullWidth = true,
}: WizardModalProps) {
  const titleId = useId();
  const { isCompact } = useAppBreakpoint();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth={fullWidth}
      fullScreen={isCompact}
      aria-labelledby={titleId}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      <DialogContent>
        <Stepper
          activeStep={activeStep}
          alternativeLabel={isCompact}
          orientation={isCompact ? 'vertical' : 'horizontal'}
          sx={{ mb: 3, pt: 1 }}
        >
          {stepLabels.map((label) => (
            <Step key={label}>
              <StepLabel>
                <Typography variant="body2">{label}</Typography>
              </StepLabel>
            </Step>
          ))}
        </Stepper>
        <Box component="div" role="region" aria-live="polite">
          {children}
        </Box>
      </DialogContent>
      <DialogActions sx={{ pb: `calc(8px + ${SAFE_AREA.bottom})`, flexWrap: 'wrap', gap: 1 }}>
        {actions}
      </DialogActions>
    </Dialog>
  );
}
