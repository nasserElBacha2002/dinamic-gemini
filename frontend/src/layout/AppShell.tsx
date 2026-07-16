/**
 * Authenticated shell — Re diseño 3.3 §4.1–4.3 + mobile temporary nav.
 *
 * **Topbar vs page header (Sprint 2.1 convention):**
 * - The topbar always shows the **screen-type** title/subtitle for the current route (§4.3). It uses
 *   `Typography` as `p`, not `h1`, so the document’s primary heading can live in the page when needed.
 * - `PageHeader` (see `components/shell/PageHeader.tsx`) is for **breadcrumbs** (§4.1, §14.1), **entity-specific
 *   titles** when the topbar stays generic (e.g. inventory name while topbar says “Inventory”), **secondary
 *   lines**, and **actions** in the main column (§4.1 “acciones contextuales en header” at page level).
 * - Top-level list/analytics routes (`/`, `/inventories`, `/metrics`): topbar shows the
 *   visible title/subtitle; `PageHeader` uses **`a11yTitle` + page actions only** so the body does not repeat the
 *   same heading. Entity/detail routes keep a visible `PageHeader` title (and breadcrumbs when applicable).
 * - Narrow/detail columns (e.g. result review) may constrain width inside `AppMain` via
 *   `DETAIL_COLUMN_MAX_WIDTH_PX` — see `components/shell/layoutConstants.ts`.
 *
 * **Responsive nav:** permanent drawer at `md+`; temporary (closed by default) below `md` with hamburger.
 */
import { Link as RouterLink, Outlet, useLocation } from 'react-router-dom';
import {
  AppBar,
  Box,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import { useTranslation } from 'react-i18next';
import { useEffect, useId, useMemo, useState } from 'react';
import { ROUTE_HOME, ROUTE_INVENTORIES_ROOT } from '../constants/appRoutes';
import { useAuth } from '../features/auth';
import {
  ADMIN_AI_CONFIG_NAV_ITEM,
  ADMIN_STORAGE_MAINTENANCE_NAV_ITEM,
  DRAWER_WIDTH,
  PRIMARY_NAV_ITEMS,
  type PrimaryNavItem,
} from './navConfig.tsx';
import { topBarCopy } from './shellTopBarCopy.ts';
import UserMenu from '../components/shell/UserMenu';
import AppMain from '../components/shell/AppMain';
import {
  SAFE_AREA,
  TOUCH_TARGET_MIN_PX,
  VIEWPORT_MIN_HEIGHT,
} from '../components/shell/layoutConstants';
import { useAppBreakpoint } from '../hooks/useAppBreakpoint';

function pathMatchesNav(to: string, pathname: string): boolean {
  if (to === ROUTE_HOME) {
    return (
      pathname === ROUTE_HOME ||
      pathname === ROUTE_INVENTORIES_ROOT ||
      pathname.startsWith(`${ROUTE_INVENTORIES_ROOT}/`)
    );
  }
  return pathname === to || pathname.startsWith(`${to}/`);
}

/**
 * Authenticated app shell — persistent left sidebar on desktop; temporary drawer on compact viewports.
 */
export default function AppShell() {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const { user } = useAuth();
  const { isDesktopShell } = useAppBreakpoint();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const navDrawerId = useId();
  const { titleKey, subtitleKey } = topBarCopy(pathname);
  const navItems = useMemo((): PrimaryNavItem[] => {
    if (user?.username === 'admin') {
      return [...PRIMARY_NAV_ITEMS, ADMIN_AI_CONFIG_NAV_ITEM, ADMIN_STORAGE_MAINTENANCE_NAV_ITEM];
    }
    return PRIMARY_NAV_ITEMS;
  }, [user?.username]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (isDesktopShell) {
      setMobileNavOpen(false);
    }
  }, [isDesktopShell]);

  const closeMobileNav = () => setMobileNavOpen(false);
  const drawerOpen = isDesktopShell || mobileNavOpen;

  return (
    <Box
      sx={{
        display: 'flex',
        minHeight: VIEWPORT_MIN_HEIGHT,
        maxWidth: '100%',
        minWidth: 0,
        bgcolor: 'background.default',
        overflowX: 'clip',
        overflowY: 'hidden',
      }}
    >
      <Drawer
        variant={isDesktopShell ? 'permanent' : 'temporary'}
        open={drawerOpen}
        onClose={closeMobileNav}
        ModalProps={{ keepMounted: true }}
        sx={{
          width: isDesktopShell ? DRAWER_WIDTH : undefined,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: isDesktopShell ? DRAWER_WIDTH : `min(${DRAWER_WIDTH}px, 100vw)`,
            boxSizing: 'border-box',
            borderRight: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
            pt: SAFE_AREA.top,
            pb: SAFE_AREA.bottom,
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
        <List dense sx={{ px: 1 }} id={navDrawerId}>
          {navItems.map((item: PrimaryNavItem) => {
            const selected = pathMatchesNav(item.to, pathname);
            return (
              <ListItemButton
                key={item.to}
                component={RouterLink}
                to={item.to}
                selected={selected}
                onClick={isDesktopShell ? undefined : closeMobileNav}
                sx={{ minHeight: TOUCH_TARGET_MIN_PX }}
              >
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

      <Box
        component="div"
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
          maxWidth: '100%',
          overflowX: 'clip',
        }}
      >
        <AppBar
          position="sticky"
          elevation={0}
          color="inherit"
          sx={{
            borderBottom: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
            maxWidth: '100%',
            minWidth: 0,
            pt: SAFE_AREA.top,
            pl: SAFE_AREA.left,
            pr: SAFE_AREA.right,
          }}
        >
          <Toolbar sx={{ gap: 1.5, minHeight: { xs: 56, sm: 64 }, px: { xs: 1, sm: 2 } }}>
            {!isDesktopShell ? (
              <IconButton
                color="inherit"
                edge="start"
                aria-label={t('shell.open_navigation')}
                aria-controls={navDrawerId}
                aria-expanded={mobileNavOpen ? 'true' : 'false'}
                onClick={() => setMobileNavOpen(true)}
                sx={{
                  minWidth: TOUCH_TARGET_MIN_PX,
                  minHeight: TOUCH_TARGET_MIN_PX,
                }}
              >
                <MenuIcon />
              </IconButton>
            ) : null}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography
                variant="h6"
                component="p"
                noWrap
                sx={{ fontSize: { xs: '1rem', sm: '1.15rem' }, fontWeight: 600 }}
              >
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

        <Box
          sx={{
            flex: 1,
            minWidth: 0,
            maxWidth: '100%',
            overflowX: 'clip',
            overflowY: 'auto',
            pb: SAFE_AREA.bottom,
          }}
        >
          <AppMain>
            <Outlet />
          </AppMain>
        </Box>
      </Box>
    </Box>
  );
}
