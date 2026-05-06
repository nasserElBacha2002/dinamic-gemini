import { Alert } from '@mui/material';
import type { ReactNode } from 'react';

type CompareNoticeProps = {
  severity: 'error' | 'info' | 'success' | 'warning';
  message?: string;
  children?: ReactNode;
  sx?: object;
  onClose?: () => void;
  testId?: string;
};

export default function CompareNotice({ severity, message, children, sx, onClose, testId }: CompareNoticeProps) {
  return (
    <Alert severity={severity} sx={sx} onClose={onClose} data-testid={testId}>
      {children ?? message}
    </Alert>
  );
}
