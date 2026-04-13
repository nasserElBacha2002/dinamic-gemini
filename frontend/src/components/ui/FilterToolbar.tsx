/**
 * FilterToolbar — **Sprint 2.3 structural base** for filter zones (Re diseño 3.3 §8.5).
 *
 * This is intentionally **minimal:** a flex row for controls (`children`), optional reset, and optional end actions.
 * Compose with `TableSearchField` for consistent search UX, or pass `TextField`, `Select`, filter chips, etc. as `children`.
 */

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Divider } from '@mui/material';

export interface FilterToolbarProps {
  children: ReactNode;
  /** Clear filters — common pattern on inventory/results tables. */
  onReset?: () => void;
  resetLabel?: string;
  resetDisabled?: boolean;
  /** Right-aligned actions (export, refresh, etc.). */
  endActions?: ReactNode;
}

export default function FilterToolbar({
  children,
  onReset,
  resetLabel,
  resetDisabled = false,
  endActions,
}: FilterToolbarProps) {
  const { t } = useTranslation();
  const resolvedResetLabel = resetLabel ?? t('common.reset_filters');
  return (
    <Box
      component="section"
      aria-label={t('common.filters_section_a11y')}
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 2,
        rowGap: 1.5,
        py: 1.5,
        px: 0,
        mb: 2,
        borderBottom: 1,
        borderColor: 'divider',
        width: '100%',
        maxWidth: '100%',
        minWidth: 0,
        boxSizing: 'border-box',
      }}
    >
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, flex: 1, minWidth: 0 }}>
        {children}
      </Box>
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'row',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 1,
          rowGap: 1,
          flexShrink: 0,
          maxWidth: '100%',
        }}
      >
        {onReset ? (
          <Button size="small" variant="text" color="inherit" onClick={onReset} disabled={resetDisabled}>
            {resolvedResetLabel}
          </Button>
        ) : null}
        {endActions ? (
          <>
            {onReset ? <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} /> : null}
            {endActions}
          </>
        ) : null}
      </Box>
    </Box>
  );
}
