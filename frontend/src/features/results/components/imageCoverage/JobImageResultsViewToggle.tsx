/**
 * Toggle between the consolidated positions table and the per-image coverage view.
 * Never replaces the positions table silently — the operator switches explicitly (`resultsView` URL param).
 */

import { useTranslation } from 'react-i18next';
import { ToggleButtonGroup, ToggleButton } from '@mui/material';
import type { AisleResultsView } from '../../utils/aisleResultsUrlFilters';

export interface JobImageResultsViewToggleProps {
  value: AisleResultsView;
  onChange: (view: AisleResultsView) => void;
}

export default function JobImageResultsViewToggle({
  value,
  onChange,
}: JobImageResultsViewToggleProps) {
  const { t } = useTranslation();
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size="small"
      onChange={(_, next: AisleResultsView | null) => {
        if (next != null) onChange(next);
      }}
      aria-label={t('results.imageCoverage.viewToggle.positions')}
    >
      <ToggleButton value="positions" data-testid="results-view-toggle-positions">
        {t('results.imageCoverage.viewToggle.positions')}
      </ToggleButton>
      <ToggleButton value="images" data-testid="results-view-toggle-images">
        {t('results.imageCoverage.viewToggle.images')}
      </ToggleButton>
    </ToggleButtonGroup>
  );
}
