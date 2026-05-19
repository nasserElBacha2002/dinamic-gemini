import type { TFunction } from 'i18next';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AnalyticsSummaryResponse } from '../../analytics/types';
import { buildMetricsKpiCards, type MetricsKpiCardViewModel } from '../../analytics/adapters/metricsViewModel';
import { numberOrZero } from '../../analytics/adapters/metricsFormatters';
import type { MetricsKpiCardView } from '../../analytics/components/MetricsKpiSection';

export interface DashboardKpiCardModel extends MetricsKpiCardView {
  grainLabel?: string;
  unavailable?: boolean;
}

/** Max KPI tiles per executive group on the Summary (Resumen) tab. */
export const EXECUTIVE_SUMMARY_KPI_LIMIT = 4;

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
