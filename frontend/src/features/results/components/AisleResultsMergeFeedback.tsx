import type { AlertColor } from '@mui/material';
import { Alert } from '@mui/material';

export interface AisleResultsMergeFeedbackProps {
  feedback: { severity: AlertColor; text: string } | null;
}

export default function AisleResultsMergeFeedback({ feedback }: AisleResultsMergeFeedbackProps) {
  if (!feedback) return null;

  return (
    <Alert severity={feedback.severity} sx={{ mb: 2 }}>
      {feedback.text}
    </Alert>
  );
}
