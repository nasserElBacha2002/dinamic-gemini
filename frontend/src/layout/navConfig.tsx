import type { ReactNode } from 'react';
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import AnalyticsOutlinedIcon from '@mui/icons-material/AnalyticsOutlined';
import PsychologyOutlinedIcon from '@mui/icons-material/PsychologyOutlined';

export const DRAWER_WIDTH = 260;

export interface PrimaryNavItem {
  /** i18n key under default namespace */
  labelKey: string;
  to: string;
  icon: ReactNode;
}

/** Primary sidebar — Inventories (home), Review queue, Metrics. */
export const PRIMARY_NAV_ITEMS: PrimaryNavItem[] = [
  { labelKey: 'nav.inventories', to: '/', icon: <Inventory2OutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.review_queue', to: '/review-queue', icon: <FactCheckOutlinedIcon fontSize="small" /> },
  { labelKey: 'nav.metrics', to: '/metrics', icon: <AnalyticsOutlinedIcon fontSize="small" /> },
];

/** Shown only when `user.username === 'admin'` (must match backend gate). */
export const ADMIN_AI_CONFIG_NAV_ITEM: PrimaryNavItem = {
  labelKey: 'nav.ai_config',
  to: '/admin/ai-config',
  icon: <PsychologyOutlinedIcon fontSize="small" />,
};
