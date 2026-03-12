/**
 * Epic 3 — Quick filter controls for the Results overview.
 */

import { ToggleButtonGroup, ToggleButton, Typography, Box } from '@mui/material';
import type { ResultsFilterKind } from '../selectors/resultsFilters';

export interface ResultsQuickFiltersProps {
  value: ResultsFilterKind;
  onChange: (filter: ResultsFilterKind) => void;
  /** Optional counts for badges (e.g. needsReview count). */
  counts?: Partial<Record<ResultsFilterKind, number>>;
}

const FILTER_OPTIONS: { value: ResultsFilterKind; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'needs_review', label: 'Needs review' },
  { value: 'valid_traceability', label: 'Valid traceability' },
  { value: 'non_valid_traceability', label: 'Non-valid traceability' },
  { value: 'qty_zero', label: 'Qty 0' },
  { value: 'low_confidence', label: 'Low confidence' },
];

export default function ResultsQuickFilters({
  value,
  onChange,
  counts,
}: ResultsQuickFiltersProps) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Filter
      </Typography>
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
            count != null && opt.value !== 'all'
              ? `${opt.label} (${count})`
              : opt.label;
          return (
            <ToggleButton key={opt.value} value={opt.value}>
              {label}
            </ToggleButton>
          );
        })}
      </ToggleButtonGroup>
    </Box>
  );
}
