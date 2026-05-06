import type { ReactNode } from 'react';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import { Box, IconButton, type BoxProps } from '@mui/material';
import type { SxProps, Theme } from '@mui/material/styles';

export interface DrawerHeaderProps {
  /** Eyebrow / context line rendered above `title` when provided. */
  overline?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  /** `aria-label` for the close control (required for accessibility). */
  closeLabel: string;
  /** Optional controls between the title column and the close button. */
  actions?: ReactNode;
  closeDisabled?: boolean;
  /** Outer sticky header row (e.g. vertical padding, stacking order). */
  sx?: SxProps<Theme>;
  closeButtonSx?: SxProps<Theme>;
}

/**
 * Presentational header row for right-hand drawers: title column, optional actions, close button.
 * Callers own typography and copy; this component only fixes layout and close affordance.
 */
export default function DrawerHeader({
  overline,
  title,
  subtitle,
  onClose,
  closeLabel,
  actions,
  closeDisabled = false,
  sx,
  closeButtonSx,
}: DrawerHeaderProps) {
  const baseHeaderSx = {
    flexShrink: 0,
    position: 'sticky',
    top: 0,
    bgcolor: 'background.paper',
    borderBottom: 1,
    borderColor: 'divider',
    px: 2.5,
    display: 'flex',
    alignItems: 'flex-start',
    gap: 1,
  } as const;

  /** MUI runtime accepts sx arrays; TS defs in this toolchain disagree on tuple unions (same pattern as `KpiCardBand`). */
  const mergedHeaderSx = (
    sx !== undefined ? [baseHeaderSx, sx] : baseHeaderSx
  ) as BoxProps['sx'];

  return (
    <Box sx={mergedHeaderSx}>
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}>
        {overline}
        {title}
        {subtitle}
      </Box>
      {actions ?? null}
      <IconButton
        aria-label={closeLabel}
        onClick={onClose}
        size="small"
        edge="end"
        disabled={closeDisabled}
        sx={closeButtonSx}
      >
        <CloseRoundedIcon fontSize="small" />
      </IconButton>
    </Box>
  );
}
