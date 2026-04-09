/**
 * Epic 4 — Loading state for Result Detail.
 */

import { useTranslation } from 'react-i18next';
import { LoadingBlock } from '../../../../components/ui';

export interface ResultDetailLoadingStateProps {
  message?: string;
}

export default function ResultDetailLoadingState({ message }: ResultDetailLoadingStateProps) {
  const { t } = useTranslation();
  return <LoadingBlock message={message ?? t('review.loading_result')} py={4} />;
}
