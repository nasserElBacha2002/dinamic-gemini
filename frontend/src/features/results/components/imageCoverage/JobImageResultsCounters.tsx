/**
 * Job image coverage counters band — Total / Con resultado / Sin resultado (API `counters`).
 */

import { useTranslation } from 'react-i18next';
import KpiCard from '../../../../components/ui/KpiCard';
import KpiCardBand from '../../../../components/ui/KpiCardBand';
import type { JobImageResultCounters } from '../../../../api/types';

export interface JobImageResultsCountersProps {
  counters: JobImageResultCounters;
}

export default function JobImageResultsCounters({ counters }: JobImageResultsCountersProps) {
  const { t } = useTranslation();
  return (
    <KpiCardBand variant="flexStrip" sx={{ mb: 2 }}>
      <KpiCard
        label={t('results.imageCoverage.counters.total')}
        value={counters.total_images}
      />
      <KpiCard
        label={t('results.imageCoverage.counters.withResult')}
        value={counters.with_result}
      />
      <KpiCard
        label={t('results.imageCoverage.counters.withoutResult')}
        value={counters.without_result}
      />
    </KpiCardBand>
  );
}
