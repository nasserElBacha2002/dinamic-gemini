/**
 * Filter chips for job image coverage — mirrors backend `result_status` (all | with_result | without_result).
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ToggleButtonGroup, ToggleButton } from '@mui/material';
import type { AisleResultsImageResultStatus } from '../../utils/aisleResultsUrlFilters';

export interface JobImageResultsStatusFilterProps {
  value: AisleResultsImageResultStatus;
  onChange: (value: AisleResultsImageResultStatus) => void;
  counts?: {
    all?: number;
    withResult?: number;
    withoutResult?: number;
  };
}

export default function JobImageResultsStatusFilter({
  value,
  onChange,
  counts,
}: JobImageResultsStatusFilterProps) {
  const { t } = useTranslation();
  const options = useMemo(
    (): { value: AisleResultsImageResultStatus; label: string; count?: number }[] => [
      { value: 'all', label: t('results.imageCoverage.statusFilter.all'), count: counts?.all },
      {
        value: 'with-result',
        label: t('results.imageCoverage.statusFilter.withResult'),
        count: counts?.withResult,
      },
      {
        value: 'without-result',
        label: t('results.imageCoverage.statusFilter.withoutResult'),
        count: counts?.withoutResult,
      },
    ],
    [t, counts?.all, counts?.withResult, counts?.withoutResult]
  );

  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size="small"
      onChange={(_, next: AisleResultsImageResultStatus | null) => {
        if (next != null) onChange(next);
      }}
      sx={{ flexWrap: 'wrap', gap: 0.5 }}
    >
      {options.map((opt) => (
        <ToggleButton key={opt.value} value={opt.value} data-testid={`image-result-status-${opt.value}`}>
          {opt.count != null ? `${opt.label} (${opt.count})` : opt.label}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
