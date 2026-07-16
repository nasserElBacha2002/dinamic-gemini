/**
 * Default card chrome for DataTable mobile rows — keep domain content in `renderMobileItem`.
 */

import type { ReactNode, MouseEvent } from 'react';
import { Box, Paper } from '@mui/material';

export interface DataTableMobileCardProps {
  children: ReactNode;
  onClick?: () => void;
  /** Accessible name when the card is a button-like row. */
  ariaLabel?: string;
}

export default function DataTableMobileCard({ children, onClick, ariaLabel }: DataTableMobileCardProps) {
  return (
    <Paper
      component={onClick ? 'button' : 'div'}
      type={onClick ? 'button' : undefined}
      variant="outlined"
      aria-label={ariaLabel}
      onClick={
        onClick
          ? (e: MouseEvent<HTMLElement>) => {
              e.preventDefault();
              onClick();
            }
          : undefined
      }
      sx={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        p: 1.5,
        borderRadius: 1,
        bgcolor: 'background.paper',
        cursor: onClick ? 'pointer' : 'default',
        border: 1,
        borderColor: 'divider',
        boxShadow: 'none',
        font: 'inherit',
        color: 'inherit',
        minWidth: 0,
        '&:focus-visible': {
          outline: (theme) => `2px solid ${theme.palette.primary.main}`,
          outlineOffset: 2,
        },
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>{children}</Box>
    </Paper>
  );
}
