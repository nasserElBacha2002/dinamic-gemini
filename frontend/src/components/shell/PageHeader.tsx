import type { ReactNode } from 'react';
import { useId, useState, type MouseEvent } from 'react';
import {
  Box,
  Breadcrumbs,
  IconButton,
  Link,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Typography,
} from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { Link as RouterLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { TOUCH_TARGET_MIN_PX } from './layoutConstants';

export interface PageHeaderBreadcrumb {
  label: string;
  to?: string;
}

export interface PageHeaderOverflowAction {
  id: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  disabledReason?: string;
  danger?: boolean;
  icon?: ReactNode;
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
  title?: ReactNode;
  /** Required when `title` is omitted: screen reader `h1` (visually hidden) so each route keeps a sensible heading. */
  a11yTitle?: string;
  subtitle?: ReactNode;
  /**
   * Internal navigation — §4.1 / §14.1. Trail links stay **secondary** by default and only pick up primary blue
   * on hover so they do not compete with page actions (§6.2: primary blue for important emphasis, not every link).
   */
  breadcrumbs?: PageHeaderBreadcrumb[];
  /**
   * Primary actions always visible (e.g. Create). Prefer this over stuffing everything into `actions`.
   * When both `primaryActions` and `actions` are set, both render (primary first).
   */
  primaryActions?: ReactNode;
  /**
   * Secondary actions moved into a “More” menu on all viewports (and especially useful on compact screens).
   */
  overflowActions?: readonly PageHeaderOverflowAction[];
  /**
   * Legacy free-form actions slot. Prefer `primaryActions` + `overflowActions` for dense headers.
   * Still supported for gradual migration.
   */
  actions?: ReactNode;
  /** Optional badge / status chip beside the title. */
  status?: ReactNode;
}

/**
 * Page-level header in the main column — Re diseño 3.3 §8.2.
 *
 * Does **not** replace the shell topbar (§4.3): the topbar carries route-wide context; this block adds
 * breadcrumbs, optional entity title, and action rows. See `layout/AppShell.tsx` file comment for the full rule.
 */
export default function PageHeader({
  title,
  a11yTitle,
  subtitle,
  breadcrumbs,
  primaryActions,
  overflowActions,
  actions,
  status,
}: PageHeaderProps) {
  const { t } = useTranslation();
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const menuId = useId();
  const menuOpen = Boolean(menuAnchor);
  const heading = title ?? a11yTitle;
  if (!title && !a11yTitle) {
    throw new Error('PageHeader: provide `title` or `a11yTitle`');
  }

  const hasOverflow = Boolean(overflowActions && overflowActions.length > 0);
  const hasAnyActions = Boolean(primaryActions || actions || hasOverflow);

  return (
    <Box
      sx={{
        mb: 3,
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        alignItems: { xs: 'stretch', sm: 'flex-start' },
        justifyContent: 'space-between',
        gap: 2,
        minWidth: 0,
        maxWidth: '100%',
      }}
    >
      <Box sx={{ minWidth: 0, flex: 1 }}>
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <Breadcrumbs
            sx={{
              mb: 1,
              maxWidth: '100%',
              '& .MuiBreadcrumbs-ol': { flexWrap: 'wrap' },
            }}
            aria-label="breadcrumb"
          >
            {breadcrumbs.map((crumb, i) =>
              crumb.to ? (
                <Link
                  key={`${crumb.label}-${i}`}
                  component={RouterLink}
                  to={crumb.to}
                  underline="hover"
                  variant="body2"
                  color="inherit"
                  sx={{
                    color: 'text.secondary',
                    fontWeight: 400,
                    overflowWrap: 'anywhere',
                    '&:hover': {
                      color: 'primary.main',
                    },
                  }}
                >
                  {crumb.label}
                </Link>
              ) : (
                <Typography
                  key={`${crumb.label}-${i}`}
                  color="text.primary"
                  variant="body2"
                  sx={{ overflowWrap: 'anywhere' }}
                >
                  {crumb.label}
                </Typography>
              ),
            )}
          </Breadcrumbs>
        ) : null}
        {title ? (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, minWidth: 0 }}>
            <Typography
              variant="h5"
              component="h1"
              gutterBottom={Boolean(subtitle) && !status}
              sx={{ overflowWrap: 'anywhere', wordBreak: 'break-word', m: 0 }}
            >
              {title}
            </Typography>
            {status}
          </Box>
        ) : (
          <Typography component="h1" sx={srOnly}>
            {heading}
          </Typography>
        )}
        {subtitle ? (
          typeof subtitle === 'string' ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: title ? 0.5 : 0, overflowWrap: 'anywhere' }}>
              {subtitle}
            </Typography>
          ) : (
            <Box sx={{ color: 'text.secondary', typography: 'body2', mt: title ? 0.5 : 0 }}>{subtitle}</Box>
          )
        ) : null}
      </Box>
      {hasAnyActions ? (
        <Box
          sx={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 1,
            alignItems: 'center',
            justifyContent: { xs: 'flex-start', sm: 'flex-end' },
            flexShrink: 0,
            maxWidth: '100%',
            minWidth: 0,
          }}
        >
          {primaryActions}
          {actions}
          {hasOverflow ? (
            <>
              <IconButton
                aria-label={t('common.more_actions')}
                aria-controls={menuOpen ? menuId : undefined}
                aria-haspopup="true"
                aria-expanded={menuOpen ? 'true' : undefined}
                onClick={(e: MouseEvent<HTMLElement>) => setMenuAnchor(e.currentTarget)}
                sx={{ minWidth: TOUCH_TARGET_MIN_PX, minHeight: TOUCH_TARGET_MIN_PX }}
              >
                <MoreVertIcon />
              </IconButton>
              <Menu
                id={menuId}
                anchorEl={menuAnchor}
                open={menuOpen}
                onClose={() => setMenuAnchor(null)}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
                PaperProps={{ sx: { minWidth: 200, maxWidth: 'min(360px, 100vw)' } }}
              >
                {overflowActions!.map((item) => (
                  <MenuItem
                    key={item.id}
                    disabled={item.disabled}
                    onClick={() => {
                      setMenuAnchor(null);
                      const fn = item.onClick;
                      window.setTimeout(() => fn(), 0);
                    }}
                  >
                    {item.icon ? (
                      <ListItemIcon sx={{ minWidth: 36, color: item.danger ? 'error.main' : 'inherit' }}>
                        {item.icon}
                      </ListItemIcon>
                    ) : null}
                    <ListItemText
                      primary={item.label}
                      secondary={item.disabled && item.disabledReason ? item.disabledReason : undefined}
                      primaryTypographyProps={{
                        variant: 'body2',
                        color: item.danger ? 'error' : 'text.primary',
                      }}
                      secondaryTypographyProps={{
                        variant: 'caption',
                        sx: { display: 'block', whiteSpace: 'normal', lineHeight: 1.35, mt: 0.25 },
                      }}
                    />
                  </MenuItem>
                ))}
              </Menu>
            </>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );
}
