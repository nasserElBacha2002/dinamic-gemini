import { Tab, Tabs } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { AnalyticsDashboardTab } from '../types';

const TAB_ORDER: AnalyticsDashboardTab[] = [
  'summary',
  'quality',
  'time',
  'providers',
  'inventories',
  'aisles',
  'compare',
  'costs',
];

const TAB_I18N: Record<AnalyticsDashboardTab, string> = {
  summary: 'analyticsDashboard.tabs.summary',
  quality: 'analyticsDashboard.tabs.quality',
  time: 'analyticsDashboard.tabs.time',
  providers: 'analyticsDashboard.tabs.providers',
  inventories: 'analyticsDashboard.tabs.inventories',
  aisles: 'analyticsDashboard.tabs.aisles',
  compare: 'analyticsDashboard.tabs.compare',
  costs: 'analyticsDashboard.tabs.costs',
};

export interface AnalyticsTabsProps {
  value: AnalyticsDashboardTab;
  onChange: (tab: AnalyticsDashboardTab) => void;
}

export function AnalyticsTabs({ value, onChange }: AnalyticsTabsProps) {
  const { t } = useTranslation();
  return (
    <Tabs
      value={value}
      onChange={(_, next: AnalyticsDashboardTab) => onChange(next)}
      variant="scrollable"
      scrollButtons="auto"
      aria-label={t('analyticsDashboard.tabs.a11y')}
      sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
    >
      {TAB_ORDER.map((tab) => (
        <Tab key={tab} value={tab} label={t(TAB_I18N[tab])} data-testid={`analytics-tab-${tab}`} />
      ))}
    </Tabs>
  );
}
