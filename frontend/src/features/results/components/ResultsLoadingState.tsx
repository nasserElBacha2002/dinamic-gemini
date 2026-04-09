/**
 * Epic 3 — Loading state for the Results overview.
 */

import { useTranslation } from 'react-i18next';
import { LoadingBlock } from '../../../components/ui';

export interface ResultsLoadingStateProps {
  message?: string;
}

export default function ResultsLoadingState({ message }: ResultsLoadingStateProps) {
  const { t } = useTranslation();
  return <LoadingBlock message={message ?? t('positions.loading_results')} py={4} />;
}
