/**
 * WizardModal — Re diseño 3.3 §8.10: guided multi-step flows (e.g. Create Inventory).
 * Provides Dialog + Stepper chrome; step body and footer actions are composed by the feature.
 */

import type { ReactNode } from 'react';
import { Box, Dialog, DialogActions, DialogContent, DialogTitle, Step, StepLabel, Stepper, Typography } from '@mui/material';
import type { DialogProps } from '@mui/material';

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
  return (
    <Dialog open={open} onClose={onClose} maxWidth={maxWidth} fullWidth={fullWidth} aria-labelledby="wizard-modal-title">
      <DialogTitle id="wizard-modal-title">{title}</DialogTitle>
      <DialogContent>
        <Stepper activeStep={activeStep} sx={{ mb: 3, pt: 1 }}>
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
      <DialogActions>{actions}</DialogActions>
    </Dialog>
  );
}
