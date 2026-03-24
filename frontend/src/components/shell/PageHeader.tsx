import type { ReactNode } from 'react';
import { Box, Breadcrumbs, Link, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export interface PageHeaderBreadcrumb {
  label: string;
  to?: string;
}

const srOnly: Record<string, string | number> = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

export interface PageHeaderProps {
  /**
   * Visible document title (`h1`). Use when the topbar only gives a **generic** screen label and the page
   * must show the **entity or section name** (e.g. inventory name while topbar says “Inventory”).
   * Omit when the topbar already fully identifies the screen and you only need breadcrumbs/actions — then set `a11yTitle`.
   */
  title?: string;
  /** Required when `title` is omitted: screen reader `h1` (visually hidden) so each route keeps a sensible heading. */
  a11yTitle?: string;
  subtitle?: ReactNode;
  /** Internal navigation — Re diseño 3.3 §4.1 / §14.1; typical above inventory/aisle flows. */
  breadcrumbs?: PageHeaderBreadcrumb[];
  /** Actions in the main column (e.g. Create inventory). §4.3 also allows primary actions in the topbar later; for Sprint 2.1 they stay here unless lifted explicitly. */
  actions?: ReactNode;
}

/**
 * Page-level header in the main column — Re diseño 3.3 §8.2.
 *
 * Does **not** replace the shell topbar (§4.3): the topbar carries route-wide context; this block adds
 * breadcrumbs, optional entity title, and action rows. See `layout/AppShell.tsx` file comment for the full rule.
 */
export default function PageHeader({ title, a11yTitle, subtitle, breadcrumbs, actions }: PageHeaderProps) {
  const heading = title ?? a11yTitle;
  if (!title && !a11yTitle) {
    throw new Error('PageHeader: provide `title` or `a11yTitle`');
  }

  return (
    <Box
      sx={{
        mb: 3,
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        alignItems: { xs: 'stretch', sm: 'flex-start' },
        justifyContent: 'space-between',
        gap: 2,
      }}
    >
      <Box sx={{ minWidth: 0, flex: 1 }}>
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <Breadcrumbs sx={{ mb: 1 }} aria-label="breadcrumb">
            {breadcrumbs.map((crumb, i) =>
              crumb.to ? (
                <Link
                  key={`${crumb.label}-${i}`}
                  component={RouterLink}
                  to={crumb.to}
                  underline="hover"
                  color="inherit"
                  variant="body2"
                >
                  {crumb.label}
                </Link>
              ) : (
                <Typography key={`${crumb.label}-${i}`} color="text.primary" variant="body2">
                  {crumb.label}
                </Typography>
              ),
            )}
          </Breadcrumbs>
        ) : null}
        {title ? (
          <Typography variant="h5" component="h1" fontWeight={600} gutterBottom={Boolean(subtitle)}>
            {title}
          </Typography>
        ) : (
          <Typography component="h1" sx={srOnly}>
            {heading}
          </Typography>
        )}
        {subtitle ? (
          typeof subtitle === 'string' ? (
            <Typography variant="body2" color="text.secondary">
              {subtitle}
            </Typography>
          ) : (
            <Box sx={{ color: 'text.secondary', typography: 'body2' }}>{subtitle}</Box>
          )
        ) : null}
      </Box>
      {actions ? (
        <Box
          sx={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 1,
            alignItems: 'center',
            justifyContent: { xs: 'flex-start', sm: 'flex-end' },
            flexShrink: 0,
          }}
        >
          {actions}
        </Box>
      ) : null}
    </Box>
  );
}
