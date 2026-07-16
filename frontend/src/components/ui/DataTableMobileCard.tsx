/**
 * Generic mobile row card for `DataTable`.
 *
 * The card is an `article`, never a `button`, so row actions, links, previews and menus
 * can live inside it without invalid nested interactive markup.
 */

import type { KeyboardEvent, MouseEvent, ReactNode } from 'react';
import { Box, Paper, Stack, Typography } from '@mui/material';
import RowActionMenu, { type RowActionMenuItem } from './RowActionMenu';

export interface DataTableMobileCardField {
  id: string;
  label: ReactNode;
  value: ReactNode;
  priority?: 'primary' | 'secondary';
  fullWidth?: boolean;
}

export interface DataTableMobileCardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  status?: ReactNode;
  fields?: readonly DataTableMobileCardField[];
  primaryAction?: ReactNode;
  actions?: readonly RowActionMenuItem[];
  onOpen?: () => void;
  ariaLabel?: string;
}

function clickTargetShouldSkipCardOpen(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return Boolean(
    target.closest(
      [
        'button',
        'a[href]',
        'input',
        'textarea',
        'select',
        '[role="button"]',
        '[role="menuitem"]',
        '[role="menu"]',
        'label',
        '[data-datatable-skip-row-click]',
      ].join(', ')
    )
  );
}

export default function DataTableMobileCard({
  title,
  subtitle,
  status,
  fields = [],
  primaryAction,
  actions,
  onOpen,
  ariaLabel,
}: DataTableMobileCardProps) {
  const interactive = Boolean(onOpen);

  const handleClick = (e: MouseEvent<HTMLElement>) => {
    if (!onOpen || clickTargetShouldSkipCardOpen(e.target)) return;
    onOpen();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (!onOpen || clickTargetShouldSkipCardOpen(e.target)) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen();
    }
  };

  return (
    <Paper
      component="article"
      variant="outlined"
      role={interactive ? 'link' : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-label={ariaLabel}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      sx={{
        display: 'block',
        width: '100%',
        p: 1.5,
        borderRadius: 1,
        bgcolor: 'background.paper',
        cursor: interactive ? 'pointer' : 'default',
        border: 1,
        borderColor: 'divider',
        boxShadow: 'none',
        color: 'inherit',
        minWidth: 0,
        '&:focus-visible': {
          outline: (theme) => `2px solid ${theme.palette.primary.main}`,
          outlineOffset: 2,
        },
      }}
    >
      <Stack spacing={1.25} sx={{ minWidth: 0 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            {title ? (
              <Typography variant="subtitle2" fontWeight={700} sx={{ overflowWrap: 'anywhere' }}>
                {title}
              </Typography>
            ) : null}
            {subtitle ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          {status ? <Box sx={{ flexShrink: 0 }}>{status}</Box> : null}
        </Stack>

        {fields.length > 0 ? (
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
              gap: 1,
              minWidth: 0,
            }}
          >
            {fields.map((field) => (
              <Box
                key={field.id}
                sx={{
                  gridColumn: field.fullWidth ? '1 / -1' : undefined,
                  minWidth: 0,
                }}
              >
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  {field.label}
                </Typography>
                <Box
                  sx={{
                    typography: field.priority === 'primary' ? 'body2' : 'caption',
                    color: field.priority === 'secondary' ? 'text.secondary' : 'text.primary',
                    overflowWrap: 'anywhere',
                    minWidth: 0,
                  }}
                >
                  {field.value}
                </Box>
              </Box>
            ))}
          </Box>
        ) : null}

        {(primaryAction || (actions && actions.length > 0)) ? (
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            gap={1}
            data-datatable-skip-row-click
          >
            <Box sx={{ minWidth: 0 }}>{primaryAction}</Box>
            {actions && actions.length > 0 ? (
              <RowActionMenu ariaLabel={ariaLabel ?? 'Row actions'} items={actions} />
            ) : null}
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}
