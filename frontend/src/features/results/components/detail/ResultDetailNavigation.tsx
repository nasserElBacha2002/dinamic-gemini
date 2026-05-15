/**
 * Epic 5 — Previous/next navigation and position indicator for Result Detail.
 */

import { useTranslation } from 'react-i18next';
import { Box, Button, Typography } from '@mui/material';
import type { ResultNavigationContext } from '../../utils/navigationContext';

export interface ResultDetailNavigationProps {
  context: ResultNavigationContext;
  onNavigate: (resultId: string) => void;
  disabled?: boolean;
}

export default function ResultDetailNavigation({
  context,
  onNavigate,
  disabled,
}: ResultDetailNavigationProps) {
  const { t } = useTranslation();
  const { currentIndex, previousId, nextId, total } = context;
  const oneBased = currentIndex + 1;

  return (
    <Box
      component="nav"
      aria-label={t('results.result_position_in_list', { current: oneBased, total })}
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1.5,
        py: 1,
        mb: 1,
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600, flex: '1 1 auto', minWidth: 0 }}>
        {t('results.result_position_in_list', { current: oneBased, total })}
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, flexShrink: 0 }}>
        <Button
          size="small"
          variant="outlined"
          disabled={disabled || !previousId}
          onClick={() => previousId && !disabled && onNavigate(previousId)}
          aria-label={t('results.prev_result')}
        >
          {t('results.navigation_previous')}
        </Button>
        <Button
          size="small"
          variant="outlined"
          disabled={disabled || !nextId}
          onClick={() => nextId && !disabled && onNavigate(nextId)}
          aria-label={t('results.next_result')}
        >
          {t('results.navigation_next')}
        </Button>
      </Box>
    </Box>
  );
}
