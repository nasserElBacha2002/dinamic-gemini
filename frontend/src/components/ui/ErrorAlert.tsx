/**
 * Error alert with optional Retry action and optional onClose.
 * Use for query errors and mutation errors that support retry.
 */

import { Alert, Button } from '@mui/material';
import { getVisibleErrorMessage, type VisibleErrorContext } from '../../utils/apiErrors';

export interface ErrorAlertProps {
  message?: string;
  error?: unknown;
  context?: VisibleErrorContext;
  /** When provided, a "Retry" button is shown in the action area. */
  onRetry?: () => void;
  retryLabel?: string;
  onClose?: () => void;
}

export default function ErrorAlert({
  message,
  error,
  context = 'default',
  onRetry,
  retryLabel = 'Retry',
  onClose,
}: ErrorAlertProps) {
  const visibleMessage = message ?? getVisibleErrorMessage(error, context);

  return (
    <Alert
      severity="error"
      sx={{ mb: 2 }}
      onClose={onClose}
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            {retryLabel}
          </Button>
        ) : undefined
      }
    >
      {visibleMessage}
    </Alert>
  );
}
