import type { ReactNode } from 'react';
import {
  ROUTE_ADMIN_AI_CONFIG,
  ROUTE_CLIENTS,
  ROUTE_HOME,
  ROUTE_INGESTION_SESSIONS,
  ROUTE_METRICS,
  ROUTE_OBSERVABILIDAD,
} from '../constants/appRoutes';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined';
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined';
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

/** Primary sidebar — Inventories (home), import sessions, metrics, observability, clients. */
export const PRIMARY_NAV_ITEMS: PrimaryNavItem[] = [
  { labelKey: 'nav.inventories', to: ROUTE_HOME, icon: <Inventory2OutlinedIcon fontSize="small" /> },
  {
    labelKey: 'nav.ingestion_sessions',
    to: ROUTE_INGESTION_SESSIONS,
    icon: <CloudUploadOutlinedIcon fontSize="small" />,
  },
  { labelKey: 'nav.metrics', to: ROUTE_METRICS, icon: <AnalyticsOutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.observability', to: ROUTE_OBSERVABILIDAD, icon: <InsightsOutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.clients', to: ROUTE_CLIENTS, icon: <BusinessRoundedIcon fontSize="small" /> },
];

/** Shown only when `user.username === 'admin'` (must match backend gate). */
export const ADMIN_AI_CONFIG_NAV_ITEM: PrimaryNavItem = {
  labelKey: 'nav.ai_config',
  to: ROUTE_ADMIN_AI_CONFIG,
  icon: <PsychologyOutlinedIcon fontSize="small" />,
};
