/**
 * Sprint 4.1 — Quick filters for Aisle Results (operational chips).
 */

import { ToggleButtonGroup, ToggleButton } from '@mui/material';
import type { ResultsFilterKind } from '../selectors/resultsFilters';

export interface ResultsQuickFiltersProps {
  value: ResultsFilterKind;
  onChange: (filter: ResultsFilterKind) => void;
  counts?: Partial<Record<ResultsFilterKind, number>>;
}

const FILTER_OPTIONS: { value: ResultsFilterKind; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'needs_review', label: 'Needs review' },
  { value: 'low_confidence', label: 'Low confidence' },
  { value: 'qty_zero', label: 'Qty zero' },
  { value: 'invalid_traceability', label: 'Invalid traceability' },
  { value: 'missing_evidence', label: 'Missing evidence' },
];

export default function ResultsQuickFilters({ value, onChange, counts }: ResultsQuickFiltersProps) {
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      onChange={(_, v) => v != null && onChange(v)}
      size="small"
      sx={{ flexWrap: 'wrap', gap: 0.5 }}
    >
      {FILTER_OPTIONS.map((opt) => {
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
