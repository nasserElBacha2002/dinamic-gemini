/**
 * Epic 4 — Loading state for Result Detail.
 */

import { LoadingBlock } from '../../../../components/ui';

export interface ResultDetailLoadingStateProps {
  message?: string;
}

export default function ResultDetailLoadingState({
  message = 'Loading result…',
}: ResultDetailLoadingStateProps) {
  return <LoadingBlock message={message} py={4} />;
}
