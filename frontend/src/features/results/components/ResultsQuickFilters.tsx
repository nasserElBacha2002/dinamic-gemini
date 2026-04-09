/**
 * Sprint 4.1 — Quick filters for Aisle Results (operational chips).
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ToggleButtonGroup, ToggleButton } from '@mui/material';
import type { ResultsFilterKind } from '../selectors/resultsFilters';

export interface ResultsQuickFiltersProps {
  value: ResultsFilterKind;
  onChange: (filter: ResultsFilterKind) => void;
  counts?: Partial<Record<ResultsFilterKind, number>>;
}

export default function ResultsQuickFilters({ value, onChange, counts }: ResultsQuickFiltersProps) {
  const { t } = useTranslation();
  const filterOptions = useMemo(
    (): { value: ResultsFilterKind; label: string }[] => [
      { value: 'all', label: t('results.filters.all') },
      { value: 'needs_review', label: t('results.filters.needs_review') },
      { value: 'low_confidence', label: t('results.filters.low_confidence') },
      { value: 'qty_zero', label: t('results.filters.qty_zero') },
      { value: 'invalid_traceability', label: t('results.filters.invalid_traceability') },
      { value: 'missing_evidence', label: t('results.filters.missing_evidence') },
    ],
    [t]
  );

  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      onChange={(_, v) => v != null && onChange(v)}
      size="small"
      sx={{ flexWrap: 'wrap', gap: 0.5 }}
    >
      {filterOptions.map((opt) => {
        const count = counts?.[opt.value];
        const label =
          count != null && opt.value !== 'all' ? `${opt.label} (${count})` : opt.label;
        return (
          <ToggleButton key={opt.value} value={opt.value}>
            {label}
          </ToggleButton>
        );
      })}
    </ToggleButtonGroup>
  );
}
