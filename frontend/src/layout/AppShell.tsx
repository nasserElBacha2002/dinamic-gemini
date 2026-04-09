/**
 * Authenticated shell — Re diseño 3.3 §4.1–4.3.
 *
 * **Topbar vs page header (Sprint 2.1 convention):**
 * - The topbar always shows the **screen-type** title/subtitle for the current route (§4.3). It uses
 *   `Typography` as `p`, not `h1`, so the document’s primary heading can live in the page when needed.
 * - `PageHeader` (see `components/shell/PageHeader.tsx`) is for **breadcrumbs** (§4.1, §14.1), **entity-specific
 *   titles** when the topbar stays generic (e.g. inventory name while topbar says “Inventory”), **secondary
 *   lines**, and **actions** in the main column (§4.1 “acciones contextuales en header” at page level).
 * - Top-level list/analytics routes (`/`, `/inventories`, `/review-queue`, `/metrics`): topbar shows the
 *   visible title/subtitle; `PageHeader` uses **`a11yTitle` + page actions only** so the body does not repeat the
 *   same heading. Entity/detail routes keep a visible `PageHeader` title (and breadcrumbs when applicable).
 * - Narrow/detail columns (e.g. result review) may constrain width inside `AppMain` via
 *   `DETAIL_COLUMN_MAX_WIDTH_PX` — see `components/shell/layoutConstants.ts`.
 */
import { Link as RouterLink, Outlet, useLocation } from 'react-router-dom';
import {
  AppBar,
  Box,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { DRAWER_WIDTH, PRIMARY_NAV_ITEMS, type PrimaryNavItem } from './navConfig.tsx';
import { topBarCopy } from './shellTopBarCopy.ts';
import UserMenu from '../components/shell/UserMenu';
import AppMain from '../components/shell/AppMain';

function pathMatchesNav(to: string, pathname: string): boolean {
  if (to === '/') {
    return pathname === '/' || pathname === '/inventories' || pathname.startsWith('/inventories/');
  }
  return pathname === to || pathname.startsWith(`${to}/`);
}

/**
 * Authenticated app shell — Re diseño 3.3 §4.1: persistent left sidebar, topbar, central main region.
 */
export default function AppShell() {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const { titleKey, subtitleKey } = topBarCopy(pathname);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
            borderRight: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
          },
        }}
      >
        <Toolbar sx={{ flexDirection: 'column', alignItems: 'flex-start', py: 2, gap: 0.5 }}>
          <Typography variant="subtitle1" fontWeight={700} component="div">
            {t('shell.brand')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('shell.operations')}
          </Typography>
        </Toolbar>
        <List dense sx={{ px: 1 }}>
          {PRIMARY_NAV_ITEMS.map((item: PrimaryNavItem) => {
            const selected = pathMatchesNav(item.to, pathname);
            return (
              <ListItemButton key={item.to} component={RouterLink} to={item.to} selected={selected}>
                <ListItemIcon sx={{ minWidth: 36, color: selected ? 'primary.main' : 'text.secondary' }}>
                  {item.icon}
                </ListItemIcon>
                <ListItemText
                  primary={t(item.labelKey)}
                  primaryTypographyProps={{ variant: 'body2', fontWeight: selected ? 600 : 400 }}
                />
              </ListItemButton>
            );
          })}
        </List>
      </Drawer>

      <Box component="div" sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <AppBar
          position="sticky"
          elevation={0}
          color="inherit"
          sx={{
            borderBottom: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        >
          <Toolbar sx={{ gap: 2, minHeight: { xs: 56, sm: 64 } }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="h6" component="p" noWrap sx={{ fontSize: { xs: '1rem', sm: '1.15rem' }, fontWeight: 600 }}>
                {t(titleKey)}
              </Typography>
              {subtitleKey ? (
                <Typography variant="caption" color="text.secondary" noWrap display="block">
                  {t(subtitleKey)}
                </Typography>
              ) : null}
            </Box>
            <UserMenu />
          </Toolbar>
        </AppBar>

        <Box sx={{ flex: 1, overflow: 'auto' }}>
          <AppMain>
            <Outlet />
          </AppMain>
        </Box>
      </Box>
    </Box>
  );
}
