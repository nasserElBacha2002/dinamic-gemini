/**
 * FilterToolbar — shared responsive filter zone.
 *
 * Desktop: primary + filters + actions inline.
 * Mobile/tablet: primary remains visible; filters move to a bottom drawer.
 */

import type { ReactNode } from 'react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Box, Button, Divider, Drawer, Stack, Typography } from '@mui/material';
import FilterListIcon from '@mui/icons-material/FilterList';
import { useAppBreakpoint } from '../../hooks/useAppBreakpoint';
import { SAFE_AREA, TOUCH_TARGET_MIN_PX } from '../shell/layoutConstants';
import DrawerHeader from './DrawerHeader';

export interface FilterToolbarProps {
  /** Always-visible primary control, usually search. */
  primary?: ReactNode;
  /** Secondary filters rendered inline on desktop and inside a drawer on compact viewports. */
  filters?: ReactNode;
  /** Right-aligned actions (export, refresh, etc.). */
  actions?: ReactNode;
  /** Clear filters — common pattern on inventory/results tables. */
  onReset?: () => void;
  resetLabel?: string;
  resetDisabled?: boolean;
  activeFilterCount?: number;
  /** Deprecated compatibility slot. Prefer `primary` / `filters`. */
  children?: ReactNode;
  /** Deprecated compatibility slot. Prefer `actions`. */
  endActions?: ReactNode;
}

export default function FilterToolbar({
  primary,
  filters,
  actions,
  onReset,
  resetLabel,
  resetDisabled = false,
  activeFilterCount = 0,
  children,
  endActions,
}: FilterToolbarProps) {
  const { t } = useTranslation();
  const { useMobileFilterDrawer } = useAppBreakpoint();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const drawerId = useId();
  const resolvedResetLabel = resetLabel ?? t('common.reset_filters');
  const resolvedPrimary = primary ?? children;
  const resolvedActions = actions ?? endActions;
  const useDrawer = Boolean(filters) && useMobileFilterDrawer;
  const filtersLabel =
    activeFilterCount > 0
      ? t('common.filters_active_count', { count: activeFilterCount })
      : t('common.filters_button');

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
        {resolvedPrimary}
        {!useDrawer ? filters : null}
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
        {useDrawer ? (
          <Button
            size="medium"
            variant="outlined"
            startIcon={<FilterListIcon />}
            onClick={() => setFiltersOpen(true)}
            aria-controls={drawerId}
            aria-expanded={filtersOpen ? 'true' : 'false'}
            sx={{ minHeight: TOUCH_TARGET_MIN_PX }}
          >
            {filtersLabel}
          </Button>
        ) : null}
        {onReset ? (
          <Button size="small" variant="text" color="inherit" onClick={onReset} disabled={resetDisabled}>
            {resolvedResetLabel}
          </Button>
        ) : null}
        {resolvedActions ? (
          <>
            {onReset || useDrawer ? <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} /> : null}
            {resolvedActions}
          </>
        ) : null}
      </Box>

      {useDrawer ? (
        <Drawer
          anchor="bottom"
          open={filtersOpen}
          onClose={() => setFiltersOpen(false)}
          PaperProps={{
            id: drawerId,
            sx: {
              maxHeight: '85dvh',
              borderTopLeftRadius: 12,
              borderTopRightRadius: 12,
              pb: SAFE_AREA.bottom,
            },
          }}
        >
          <DrawerHeader
            title={<Typography variant="h6">{t('common.filters_button')}</Typography>}
            onClose={() => setFiltersOpen(false)}
            closeLabel={t('common.close')}
          />
          <Stack spacing={2} sx={{ p: 2, pt: 0, minWidth: 0 }}>
            {filters}
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {onReset ? (
                <Button variant="text" onClick={onReset} disabled={resetDisabled}>
                  {resolvedResetLabel}
                </Button>
              ) : null}
              <Button variant="contained" onClick={() => setFiltersOpen(false)}>
                {t('common.close')}
              </Button>
            </Box>
          </Stack>
        </Drawer>
      ) : null}
    </Box>
  );
}
