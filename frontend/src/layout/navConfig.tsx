import type { ReactNode } from 'react';
import {
  ROUTE_ADMIN_AI_CONFIG,
  ROUTE_CLIENTS,
  ROUTE_HOME,
  ROUTE_INGESTION_SESSIONS,
  ROUTE_METRICS,
  ROUTE_REVIEW_QUEUE,
} from '../constants/appRoutes';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import BusinessRoundedIcon from '@mui/icons-material/BusinessRounded';

export const DRAWER_WIDTH = 260;

export interface PrimaryNavItem {
  /** i18n key under default namespace */
  labelKey: string;
  to: string;
  icon: ReactNode;
}

/** Primary sidebar — Inventories (home), Review queue, Metrics. */
export const PRIMARY_NAV_ITEMS: PrimaryNavItem[] = [
  { labelKey: 'nav.inventories', to: ROUTE_HOME, icon: <Inventory2OutlinedIcon fontSize="small" /> },
  {
    labelKey: 'nav.ingestion_sessions',
    to: ROUTE_INGESTION_SESSIONS,
    icon: <CloudUploadOutlinedIcon fontSize="small" />,
  },
  { labelKey: 'nav.review_queue', to: ROUTE_REVIEW_QUEUE, icon: <FactCheckOutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.metrics', to: ROUTE_METRICS, icon: <AnalyticsOutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.clients', to: ROUTE_CLIENTS, icon: <BusinessRoundedIcon fontSize="small" /> },
];

/** Shown only when `user.username === 'admin'` (must match backend gate). */
export const ADMIN_AI_CONFIG_NAV_ITEM: PrimaryNavItem = {
  labelKey: 'nav.ai_config',
  to: ROUTE_ADMIN_AI_CONFIG,
  icon: <PsychologyOutlinedIcon fontSize="small" />,
};
