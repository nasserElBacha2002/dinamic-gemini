/**
 * Epic 3 — Results overview page header.
 *
 * Route-level label (“Aisle results”) is in `AppShell`’s topbar (`p`). This heading is the **document `h1`**
 * for this screen (result list for the aisle). See `layout/AppShell.tsx` for shell vs page header rules.
 */

import { useTranslation } from 'react-i18next';
import { Button, Typography, Box } from '@mui/material';

export interface ResultsOverviewHeaderProps {
  title?: string;
  /** Optional context line (e.g. aisle code or job id). */
  context?: string;
  onBack?: () => void;
  backLabel?: string;
}

export default function ResultsOverviewHeader({
  title,
  context,
  onBack,
  backLabel,
}: ResultsOverviewHeaderProps) {
  const { t } = useTranslation();
  const resolvedTitle = title ?? t('positions.title_results');
  const resolvedBackLabel = backLabel ?? t('results.overview_back_inventory');
  return (
    <Box sx={{ mb: 3 }}>
      {onBack && (
        <Button sx={{ mb: 1.5 }} onClick={onBack}>
          ← {resolvedBackLabel}
        </Button>
      )}
      <Typography variant="h5" component="h1">
        {resolvedTitle}
      </Typography>
      {context && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {context}
        </Typography>
      )}
    </Box>
  );
}
