/**
 * Epic 4 — Error state for Result Detail.
 */

import { ErrorAlert } from '../../../../components/ui';

export interface ResultDetailErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export default function ResultDetailErrorState({
  message,
  onRetry,
}: ResultDetailErrorStateProps) {
  return <ErrorAlert message={message} onRetry={onRetry} />;
}
