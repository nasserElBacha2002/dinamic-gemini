/**
 * FilterToolbar — **Sprint 2.3 structural base** for filter zones (Re diseño 3.3 §8.5).
 *
 * This is intentionally **minimal:** a flex row for controls (`children`), optional reset, and optional end actions.
 * It is **not** the final “smart” table toolbar (no built-in search field, chip state, or query wiring) — those land
 * with Sprint 2.4+ screens and `FilterToolbar` composition. Pass `TextField`, `Select`, filter chips, etc. as `children`.
 */

import type { ReactNode } from 'react';
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
  resetLabel = 'Reset filters',
  resetDisabled = false,
  endActions,
}: FilterToolbarProps) {
  return (
    <Box
      component="section"
      aria-label="Filters"
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 2,
        py: 1.5,
        px: 0,
        mb: 2,
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, flex: 1, minWidth: 0 }}>
        {children}
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 1, flexShrink: 0 }}>
        {onReset ? (
          <Button size="small" variant="text" color="inherit" onClick={onReset} disabled={resetDisabled}>
            {resetLabel}
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
