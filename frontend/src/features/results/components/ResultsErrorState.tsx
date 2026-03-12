/**
 * Epic 3 — Error state for the Results overview.
 */

import { ErrorAlert } from '../../../components/ui';

export interface ResultsErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export default function ResultsErrorState({
  message,
  onRetry,
}: ResultsErrorStateProps) {
  return <ErrorAlert message={message} onRetry={onRetry} />;
}
