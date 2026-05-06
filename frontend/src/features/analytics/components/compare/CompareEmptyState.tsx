import { Alert } from '@mui/material';

type CompareEmptyStateProps = {
  message: string;
  severity?: 'info' | 'warning' | 'success';
  testId?: string;
};

export default function CompareEmptyState({ message, severity = 'info', testId }: CompareEmptyStateProps) {
  return (
    <Alert severity={severity} data-testid={testId}>
      {message}
    </Alert>
  );
}
