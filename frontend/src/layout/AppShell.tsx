import { Link as RouterLink, Outlet, useLocation, matchPath } from 'react-router-dom';
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
import { DRAWER_WIDTH, PRIMARY_NAV_ITEMS } from './navConfig';
import UserMenu from '../components/shell/UserMenu';
import AppMain from '../components/shell/AppMain';

function pathMatchesNav(to: string, pathname: string): boolean {
  if (to === '/inventories') {
    return pathname === '/inventories' || pathname.startsWith('/inventories/');
  }
  return pathname === to || pathname.startsWith(`${to}/`);
}

/** Topbar title derived from route — Re diseño 3.3 §4.3 contextual page title. */
function topBarCopy(pathname: string): { title: string; subtitle?: string } {
  if (pathname === '/dashboard') {
    return { title: 'Dashboard', subtitle: 'Operational overview' };
  }
  if (pathname === '/inventories') {
    return { title: 'Inventories', subtitle: 'Manage all inventories' };
  }
  if (pathname.startsWith('/inventories/')) {
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/positions/:positionId', pathname)) {
      return { title: 'Result review', subtitle: 'Evidence and review actions' };
    }
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/positions', pathname)) {
      return { title: 'Aisle results', subtitle: 'Prioritize review' };
    }
    if (matchPath('/inventories/:inventoryId', pathname)) {
      return { title: 'Inventory', subtitle: 'Aisles and processing' };
    }
  }
  if (pathname === '/review-queue') {
    return { title: 'Review queue', subtitle: 'Cross-inventory results' };
  }
  if (pathname === '/metrics') {
    return { title: 'Metrics', subtitle: 'Analytics and performance' };
  }
  if (pathname === '/settings') {
    return { title: 'Settings', subtitle: 'Preferences' };
  }
  return { title: 'Dinamic Inventory', subtitle: 'v3' };
}

/**
 * Authenticated app shell — Re diseño 3.3 §4.1: persistent left sidebar, topbar, central main region.
 */
export default function AppShell() {
  const { pathname } = useLocation();
  const { title, subtitle } = topBarCopy(pathname);

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
            Dinamic Inventory
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Operations
          </Typography>
        </Toolbar>
        <List dense sx={{ px: 1 }}>
          {PRIMARY_NAV_ITEMS.map((item) => {
            const selected = pathMatchesNav(item.to, pathname);
            return (
              <ListItemButton key={item.to} component={RouterLink} to={item.to} selected={selected}>
                <ListItemIcon sx={{ minWidth: 36, color: selected ? 'primary.main' : 'text.secondary' }}>
                  {item.icon}
                </ListItemIcon>
                <ListItemText primary={item.label} primaryTypographyProps={{ variant: 'body2', fontWeight: selected ? 600 : 400 }} />
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
                {title}
              </Typography>
              {subtitle ? (
                <Typography variant="caption" color="text.secondary" noWrap display="block">
                  {subtitle}
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
