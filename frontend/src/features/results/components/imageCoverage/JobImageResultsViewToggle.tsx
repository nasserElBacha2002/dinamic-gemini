/**
 * Toggle between positions table and unmatched-images queue.
 * Images tab is disabled when there are no pending images (`without_result === 0`).
 */

import { useTranslation } from 'react-i18next';
import { ToggleButtonGroup, ToggleButton } from '@mui/material';
import type { AisleResultsView } from '../../utils/aisleResultsUrlFilters';

export interface JobImageResultsViewToggleProps {
  value: AisleResultsView;
  onChange: (view: AisleResultsView) => void;
  withoutResultCount?: number;
  imagesDisabled?: boolean;
}

export default function JobImageResultsViewToggle({
  value,
  onChange,
  withoutResultCount = 0,
  imagesDisabled = false,
}: JobImageResultsViewToggleProps) {
  const { t } = useTranslation();
  const imagesLabel =
    withoutResultCount > 0
      ? t('results.imageCoverage.viewToggle.unmatchedWithCount', { count: withoutResultCount })
      : t('results.imageCoverage.viewToggle.unmatched');

  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size="small"
      onChange={(_, next: AisleResultsView | null) => {
        if (next == null) return;
        if (next === 'images' && imagesDisabled) return;
        onChange(next);
      }}
      aria-label={t('results.imageCoverage.viewToggle.aria')}
    >
      <ToggleButton value="positions" data-testid="results-view-toggle-positions">
        {t('results.imageCoverage.viewToggle.positions')}
      </ToggleButton>
      <ToggleButton
        value="images"
        disabled={imagesDisabled}
        data-testid="results-view-toggle-images"
        aria-disabled={imagesDisabled}
      >
        {imagesLabel}
      </ToggleButton>
    </ToggleButtonGroup>
  );
}
