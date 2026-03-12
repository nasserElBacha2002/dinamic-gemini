/**
 * Epic 3 — Loading state for the Results overview.
 */

import { LoadingBlock } from '../../../components/ui';

export interface ResultsLoadingStateProps {
  message?: string;
}

export default function ResultsLoadingState({
  message = 'Loading results…',
}: ResultsLoadingStateProps) {
  return <LoadingBlock message={message} py={4} />;
}
