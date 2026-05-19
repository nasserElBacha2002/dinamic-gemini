import type { TFunction } from 'i18next';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsSummaryResponse } from '../../analytics/types';
import { buildMetricsKpiCards, type MetricsKpiCardViewModel } from '../../analytics/adapters/metricsViewModel';
import { formatPct, numberOrZero } from '../../analytics/adapters/metricsFormatters';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import { formatMetricValue } from './analyticsCostFormatters';
import type { MetricsKpiCardView } from '../../analytics/adapters/metricsViewModel';

export interface DashboardKpiCardModel extends MetricsKpiCardView {
  grainLabel?: string;
  unavailable?: boolean;
}

/** Max KPI tiles per executive group on the Summary (Resumen) tab. */
export const EXECUTIVE_SUMMARY_KPI_LIMIT = 4;

/** Max KPI tiles in the Resumen executive hero (3 primary + 3 secondary). */
export const HERO_EXECUTIVE_KPI_LIMIT = 6;

export interface HeroKpiModel {
  id: string;
  label: string;
  value: string;
  tier: 'primary' | 'secondary';
  unavailable?: boolean;
}

function pctObs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)} %`;
}

export function buildPositionSummaryKpis(
  summary: AnalyticsSummaryResponse | null | undefined,
  hasUnidentifiedProductRate: boolean,
  t: TFunction
): DashboardKpiCardModel[] {
  const grain = t('analyticsDashboard.grain_positions');
  const metricsCards = buildMetricsKpiCards(summary, hasUnidentifiedProductRate, t);
  const processed: DashboardKpiCardModel = {
    grainLabel: grain,
    label: t('analyticsDashboard.kpi_positions_processed'),
    value: String(numberOrZero(summary?.processed_positions_count)),
    description: t('analyticsDashboard.kpi_positions_processed_desc'),
  };
  return [
    processed,
    ...metricsCards.map((card: MetricsKpiCardViewModel) => ({
      grainLabel: grain,
      label: card.label,
      value: card.value,
      description: card.description,
    })),
  ];
}

export function buildExecutivePositionKpis(
  summary: AnalyticsSummaryResponse | null | undefined,
  hasUnidentifiedProductRate: boolean,
  t: TFunction
): DashboardKpiCardModel[] {
  const grain = t('analyticsDashboard.grain_positions');
  const metricsCards = buildMetricsKpiCards(summary, hasUnidentifiedProductRate, t);
  const findMetric = (label: string) => metricsCards.find((card) => card.label === label);

  const processed: DashboardKpiCardModel = {
    grainLabel: grain,
    label: t('analyticsDashboard.kpi_positions_processed'),
    value: String(numberOrZero(summary?.processed_positions_count)),
    description: t('analyticsDashboard.kpi_positions_processed_desc'),
  };

  const auto = findMetric(t('analytics.kpi_auto_accept_title'));
  const manual = findMetric(t('analytics.kpi_manual_correction_title'));
  const avgProcessing = findMetric(t('analytics.kpi_avg_processing_title'));

  return [
    processed,
    ...(auto
      ? [{ grainLabel: grain, label: auto.label, value: auto.value, description: auto.description }]
      : []),
    ...(manual
      ? [{ grainLabel: grain, label: manual.label, value: manual.value, description: manual.description }]
      : []),
    ...(avgProcessing
      ? [
          {
            grainLabel: grain,
            label: avgProcessing.label,
            value: avgProcessing.value,
            description: avgProcessing.description,
          },
        ]
      : []),
  ].slice(0, EXECUTIVE_SUMMARY_KPI_LIMIT);
}

export function buildExecutiveRunKpis(
  data: ObservabilityMetricsResponse | null | undefined,
  t: TFunction
): DashboardKpiCardModel[] {
  return buildRunSummaryKpis(data, t).slice(0, EXECUTIVE_SUMMARY_KPI_LIMIT);
}

export function buildHeroExecutiveKpis(
  summary: AnalyticsSummaryResponse | null | undefined,
  observability: ObservabilityMetricsResponse | null | undefined,
  costSummary: AnalyticsCostSummaryResponse | null | undefined,
  t: TFunction,
  options: { costAvailable: boolean }
): HeroKpiModel[] {
  const totals = observability?.totals;
  const costTotals = costSummary?.totals;
  const unavailable = t('analyticsDashboard.costs.notAvailable');

  const primary: HeroKpiModel[] = [
    {
      id: 'processed',
      label: t('analyticsDashboard.kpi_positions_processed'),
      value: String(numberOrZero(summary?.processed_positions_count)),
      tier: 'primary',
    },
    {
      id: 'total-cost',
      label: t('analyticsDashboard.costs.totalCost'),
      value:
        options.costAvailable && costTotals?.total_cost != null
          ? formatMetricValue(costTotals.total_cost, 'cost')
          : unavailable,
      tier: 'primary',
      unavailable: !options.costAvailable || costTotals?.total_cost == null,
    },
    {
      id: 'auto-accept',
      label: t('analytics.kpi_auto_accept_title'),
      value: formatPct(summary?.auto_acceptance_rate),
      tier: 'primary',
    },
  ];

  const costPerUnit =
    options.costAvailable && costTotals?.cost_per_counted_unit != null
      ? formatMetricValue(costTotals.cost_per_counted_unit, 'costPerUnit')
      : costTotals?.total_counted_quantity != null
        ? formatMetricValue(costTotals.total_counted_quantity, 'quantity')
        : unavailable;

  const secondary: HeroKpiModel[] = [
    {
      id: 'cost-per-unit',
      label: t('analyticsDashboard.costs.costPerUnit'),
      value: costPerUnit,
      tier: 'secondary',
      unavailable:
        !options.costAvailable ||
        (costTotals?.cost_per_counted_unit == null && costTotals?.total_counted_quantity == null),
    },
    {
      id: 'runs-succeeded',
      label: t('observability.metrics.kpiSucceeded'),
      value: totals?.runs_succeeded != null ? String(totals.runs_succeeded) : '—',
      tier: 'secondary',
    },
    {
      id: 'failure-rate',
      label: t('observability.metrics.kpiFailureRate'),
      value: pctObs(totals?.failure_rate),
      tier: 'secondary',
    },
  ];

  return [...primary, ...secondary].slice(0, HERO_EXECUTIVE_KPI_LIMIT);
}

export function buildRunSummaryKpis(
  data: ObservabilityMetricsResponse | null | undefined,
  t: TFunction
): DashboardKpiCardModel[] {
  const totals = data?.totals;
  const dq = data?.data_quality;
  if (!totals) return [];
  const grain = t('analyticsDashboard.grain_runs');
  return [
    { grainLabel: grain, label: t('observability.metrics.kpiRuns'), value: totals.runs_total },
    { grainLabel: grain, label: t('observability.metrics.kpiSucceeded'), value: totals.runs_succeeded },
    { grainLabel: grain, label: t('observability.metrics.kpiFailed'), value: totals.runs_failed },
    { grainLabel: grain, label: t('observability.metrics.kpiFailureRate'), value: pctObs(totals.failure_rate) },
    { grainLabel: grain, label: t('observability.metrics.kpiLegacy'), value: totals.legacy_runs },
    { grainLabel: grain, label: t('observability.metrics.kpiMissingRef'), value: totals.missing_reference_runs },
    {
      grainLabel: grain,
      label: t('analyticsDashboard.kpi_jobs_without_snapshot'),
      value: dq?.jobs_without_audit_snapshot ?? 0,
    },
    { grainLabel: grain, label: t('observability.metrics.kpiMissingPrompt'), value: totals.missing_prompt_config_runs },
  ];
}

export function buildUnavailableGlobalCostKpis(t: TFunction): DashboardKpiCardModel[] {
  const labels = [
    t('analyticsDashboard.costs.totalCost'),
    t('analyticsDashboard.costs.totalQuantity'),
    t('analyticsDashboard.costs.costPerUnit'),
    t('analyticsDashboard.costs.costPerProvider'),
    t('analyticsDashboard.costs.costPerAisle'),
  ];
  return labels.map((label) => ({
    label,
    value: t('analyticsDashboard.costs.unavailableCard'),
    description: t('analyticsDashboard.costs.unavailableExplain'),
    unavailable: true,
  }));
}

export function hasUnidentifiedProductRate(summary: AnalyticsSummaryResponse | null | undefined): boolean {
  return summary?.unidentified_product_rate != null;
}
