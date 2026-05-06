/**
 * KpiCardBand — presentational wrapper for horizontal/grid KPI bands (§8.3 composition).
 * No domain data; consumers render `KpiCard` children as today.
 */

import type { ReactNode } from 'react';
import { Box, type BoxProps } from '@mui/material';
import type { SxProps, Theme } from '@mui/material/styles';

/** Layout presets mirror existing bands — do not change tokens without visual QA. */
export type KpiCardBandVariant = 'flexStrip' | 'responsiveGrid' | 'metricsGrid';

export interface KpiCardBandProps {
  children: ReactNode;
  variant?: KpiCardBandVariant;
  sx?: SxProps<Theme>;
}

const VARIANT_SX: Record<KpiCardBandVariant, SxProps<Theme>> = {
  /** Aisle results KPI strip — flex + fixed basis per card. */
  flexStrip: {
    display: 'flex',
    flexWrap: { xs: 'wrap', md: 'nowrap' },
    gap: 1.5,
    overflowX: { xs: 'visible', md: 'auto' },
    width: '100%',
    minWidth: 0,
    mb: 2,
    alignItems: 'stretch',
  },
  /** Review queue summary grid — 2 / 3 / 5 columns. */
  responsiveGrid: {
    display: 'grid',
    gridTemplateColumns: {
      xs: 'repeat(2, minmax(0, 1fr))',
      sm: 'repeat(3, minmax(0, 1fr))',
      md: 'repeat(5, minmax(0, 1fr))',
    },
    gap: 1.5,
    width: '100%',
    minWidth: 0,
    mb: 2,
    alignItems: 'stretch',
  },
  /** Analytics dashboard KPI grid — 1 / 2 / 3 columns, wider gap. */
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: {
      xs: 'minmax(0, 1fr)',
      sm: 'repeat(2, minmax(0, 1fr))',
      md: 'repeat(3, minmax(0, 1fr))',
    },
    gap: 2,
    mb: 2,
    minWidth: 0,
    width: '100%',
  },
};

export default function KpiCardBand({ children, variant = 'flexStrip', sx }: KpiCardBandProps) {
  /** MUI runtime accepts sx arrays; TS defs in this toolchain disagree on tuple unions. */
  const mergedSx = (sx ? [VARIANT_SX[variant], sx] : VARIANT_SX[variant]) as BoxProps['sx'];
  return <Box sx={mergedSx}>{children}</Box>;
}
