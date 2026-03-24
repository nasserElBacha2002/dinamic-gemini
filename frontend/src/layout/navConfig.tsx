import type { ReactNode } from 'react';
import DashboardRoundedIcon from '@mui/icons-material/DashboardRounded';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';

export const DRAWER_WIDTH = 260;

export interface PrimaryNavItem {
  label: string;
  to: string;
  icon: ReactNode;
}

/** Primary sidebar destinations — aligned with Re diseño 3.3 §4.2 (Dashboard, Inventories, Review Queue, Metrics, Settings). */
export const PRIMARY_NAV_ITEMS: PrimaryNavItem[] = [
  { label: 'Dashboard', to: '/dashboard', icon: <DashboardRoundedIcon fontSize="small" /> },
  { label: 'Inventories', to: '/inventories', icon: <Inventory2OutlinedIcon fontSize="small" /> },
  { label: 'Review queue', to: '/review-queue', icon: <FactCheckOutlinedIcon fontSize="small" /> },
  { label: 'Metrics', to: '/metrics', icon: <AnalyticsOutlinedIcon fontSize="small" /> },
  { label: 'Settings', to: '/settings', icon: <SettingsOutlinedIcon fontSize="small" /> },
];
