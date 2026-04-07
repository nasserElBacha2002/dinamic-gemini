import type { ReactNode } from 'react';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined';

export const DRAWER_WIDTH = 260;

export interface PrimaryNavItem {
  label: string;
  to: string;
  icon: ReactNode;
}

/** Primary sidebar — Inventories (home), Review queue, Metrics. */
export const PRIMARY_NAV_ITEMS: PrimaryNavItem[] = [
  { label: 'Inventories', to: '/', icon: <Inventory2OutlinedIcon fontSize="small" /> },
  { label: 'Review queue', to: '/review-queue', icon: <FactCheckOutlinedIcon fontSize="small" /> },
  { label: 'Metrics', to: '/metrics', icon: <AnalyticsOutlinedIcon fontSize="small" /> },
];
