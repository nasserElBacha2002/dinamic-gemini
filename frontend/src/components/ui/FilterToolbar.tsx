/**
 * FilterToolbar — **Sprint 2.3 structural base** for filter zones (Re diseño 3.3 §8.5) + mobile drawer.
 *
 * This is intentionally **minimal:** a flex row for controls (`children`), optional reset, and optional end actions.
 * Compose with `TableSearchField` for consistent search UX, or pass `TextField`, `Select`, filter chips, etc. as `children`.
 *
 * On compact viewports, when `mobileSecondaryFilters` is provided, secondary filters open in a bottom drawer
 * while `children` (typically search) stay visible.
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
  children: ReactNode;
  /** Clear filters — common pattern on inventory/results tables. */
  onReset?: () => void;
  resetLabel?: string;
  resetDisabled?: boolean;
  /** Right-aligned actions (export, refresh, etc.). */
  endActions?: ReactNode;
  /**
   * Secondary filters shown inline on desktop; on compact viewports they open via the Filters button.
   * When omitted, `children` always render inline (existing behavior).
   */
  mobileSecondaryFilters?: ReactNode;
  /** Count of active secondary filters (shown on the Filters button badge). */
  activeFilterCount?: number;
}

export default function FilterToolbar({
  children,
  onReset,
  resetLabel,
  resetDisabled = false,
  endActions,
  mobileSecondaryFilters,
  activeFilterCount = 0,
}: FilterToolbarProps) {
  const { t } = useTranslation();
  const { isCompact } = useAppBreakpoint();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const drawerId = useId();
  const resolvedResetLabel = resetLabel ?? t('common.reset_filters');
  const useMobileDrawer = Boolean(mobileSecondaryFilters) && isCompact;
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
        {children}
        {!useMobileDrawer && mobileSecondaryFilters ? mobileSecondaryFilters : null}
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
        {useMobileDrawer ? (
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
        {endActions ? (
          <>
            {onReset || useMobileDrawer ? <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} /> : null}
            {endActions}
          </>
        ) : null}
      </Box>

      {useMobileDrawer ? (
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
            {mobileSecondaryFilters}
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {onReset ? (
                <Button
                  variant="text"
                  onClick={() => {
                    onReset();
                  }}
                  disabled={resetDisabled}
                >
                  {resolvedResetLabel}
                </Button>
              ) : null}
              <Button variant="contained" onClick={() => setFiltersOpen(false)}>
                {t('common.close')}
              </Button>
            </Box>
            <Typography variant="caption" color="text.secondary">
              {t('common.filters_section_a11y')}
            </Typography>
          </Stack>
        </Drawer>
      ) : null}
    </Box>
  );
}
