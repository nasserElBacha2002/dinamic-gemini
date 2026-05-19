import { ROUTE_ANALITICA } from './appRoutes';
import type { AnalyticsDashboardTab } from '../features/analytics-dashboard/types';

export const ANALYTICS_TAB_QUERY_KEY = 'tab';

export type AnalyticsTabUrlId =
  | 'resumen'
  | 'costos'
  | 'calidad'
  | 'tiempos'
  | 'proveedores'
  | 'inventarios'
  | 'pasillos'
  | 'comparacion';

const URL_TO_INTERNAL: Record<AnalyticsTabUrlId, AnalyticsDashboardTab> = {
  resumen: 'summary',
  costos: 'costs',
  calidad: 'quality',
  tiempos: 'time',
  proveedores: 'providers',
  inventarios: 'inventories',
  pasillos: 'aisles',
  comparacion: 'compare',
};

const INTERNAL_TO_URL: Record<AnalyticsDashboardTab, AnalyticsTabUrlId> = {
  summary: 'resumen',
  costs: 'costos',
  quality: 'calidad',
  time: 'tiempos',
  providers: 'proveedores',
  inventories: 'inventarios',
  aisles: 'pasillos',
  compare: 'comparacion',
};

const VALID_URL_TABS = new Set<string>(Object.keys(URL_TO_INTERNAL));

export function parseAnalyticsTab(value: string | null): AnalyticsDashboardTab {
  if (!value) return 'summary';
  const normalized = value.trim().toLowerCase();
  if (!VALID_URL_TABS.has(normalized)) return 'summary';
  return URL_TO_INTERNAL[normalized as AnalyticsTabUrlId];
}

export function analyticsTabToUrl(tab: AnalyticsDashboardTab): AnalyticsTabUrlId {
  return INTERNAL_TO_URL[tab];
}

export function pathToAnalytics(tab?: AnalyticsDashboardTab): string {
  const urlTab = analyticsTabToUrl(tab ?? 'summary');
  return `${ROUTE_ANALITICA}?${ANALYTICS_TAB_QUERY_KEY}=${urlTab}`;
}
