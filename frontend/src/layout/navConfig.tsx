import type { ReactNode } from 'react';
import {
  ROUTE_ADMIN_AI_CONFIG,
  ROUTE_ADMIN_STORAGE_MAINTENANCE,
  ROUTE_CLIENTS,
  ROUTE_HOME,
  pathToAnalytics,
} from '../constants/appRoutes';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import CleaningServicesOutlinedIcon from '@mui/icons-material/CleaningServicesOutlined';
import BusinessRoundedIcon from '@mui/icons-material/BusinessRounded';
import { DRAWER_WIDTH_PX } from '../components/shell/layoutConstants';

/** @deprecated Prefer `DRAWER_WIDTH_PX` from layoutConstants — kept for existing imports. */
export const DRAWER_WIDTH = DRAWER_WIDTH_PX;

export interface PrimaryNavItem {
  /** i18n key under default namespace */
  labelKey: string;
  to: string;
  icon: ReactNode;
}

/** Primary sidebar — Inventories (home), analytics, clients. Photo upload: Inventario → Pasillo. */
export const PRIMARY_NAV_ITEMS: PrimaryNavItem[] = [
  { labelKey: 'nav.inventories', to: ROUTE_HOME, icon: <Inventory2OutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.analytics', to: pathToAnalytics('summary'), icon: <AnalyticsOutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.clients', to: ROUTE_CLIENTS, icon: <BusinessRoundedIcon fontSize="small" /> },
];

/** Shown only when `user.username === 'admin'` (must match backend gate). */
export const ADMIN_AI_CONFIG_NAV_ITEM: PrimaryNavItem = {
  labelKey: 'nav.ai_config',
  to: ROUTE_ADMIN_AI_CONFIG,
  icon: <PsychologyOutlinedIcon fontSize="small" />,
};

export const ADMIN_STORAGE_MAINTENANCE_NAV_ITEM: PrimaryNavItem = {
  labelKey: 'nav.storage_maintenance',
  to: ROUTE_ADMIN_STORAGE_MAINTENANCE,
  icon: <CleaningServicesOutlinedIcon fontSize="small" />,
};
