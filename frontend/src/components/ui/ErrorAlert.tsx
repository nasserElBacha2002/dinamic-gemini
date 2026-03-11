/**
 * Error alert with optional Retry action and optional onClose.
 * Use for query errors and mutation errors that support retry.
 */

import { Alert, Button } from '@mui/material';

export interface ErrorAlertProps {
  message: string;
  /** When provided, a "Retry" button is shown in the action area. */
  onRetry?: () => void;
  onClose?: () => void;
}

export default function ErrorAlert({ message, onRetry, onClose }: ErrorAlertProps) {
  return (
    <Alert
      severity="error"
      sx={{ mb: 2 }}
      onClose={onClose}
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            Retry
          </Button>
        ) : undefined
      }
    >
      {message}
    </Alert>
  );
}
