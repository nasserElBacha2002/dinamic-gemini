import type { TFunction } from 'i18next';
import type { AnalyticsCostSummaryResponse } from '../../../api/types';
import type { ObservabilityMetricsResponse } from '../../../api/types';
import type { AisleIssueRow, InventoryPerformanceRow } from '../../analytics/types';
import { pathToAislePositions, pathToInventory, pathToInventoryAnalyticsCompareMany } from '../../../constants/appRoutes';
import { formatAvgProcessingMinutes, formatPct } from '../../analytics/adapters/metricsFormatters';
import type { AnalyticsEntityAction } from '../components/actions/AnalyticsEntityActionRow';
import type { AnalyticsEntityRankingCardItem } from '../components/rankings/AnalyticsEntityRankingCards';
import type { AnalyticsMetadataItem } from '../components/base/AnalyticsMetadataGrid';
import { buildAisleEntityKey } from './aisleEntityKeys';
import { formatCostCell, formatCostCellWithLoading } from './analyticsCostViewModel';
import { compareEligibilityTooltipKey, getCompareEligibility } from '../types';

type InventoryCostRow = AnalyticsCostSummaryResponse['by_inventory'][number];
type AisleCostRow = AnalyticsCostSummaryResponse['by_aisle'][number];
type ProviderRow = ObservabilityMetricsResponse['by_provider_model'][number];

function costMetadataItems(
  t: TFunction,
  cost: { total_cost?: number | null; total_counted_quantity?: number | null; cost_per_counted_unit?: number | null } | undefined,
  isCostLoading: boolean,
  prefix: string
): AnalyticsMetadataItem[] {
  return [
    {
      id: `${prefix}-total-cost`,
      label: t('analyticsDashboard.costs.totalCost'),
      value: formatCostCellWithLoading(isCostLoading, cost?.total_cost, 'cost', t),
    },
    {
      id: `${prefix}-total-qty`,
      label: t('analyticsDashboard.costs.totalQuantity'),
      value: formatCostCellWithLoading(isCostLoading, cost?.total_counted_quantity, 'quantity', t),
    },
    {
      id: `${prefix}-cpu`,
      label: t('analyticsDashboard.costs.costPerUnit'),
      value: formatCostCellWithLoading(isCostLoading, cost?.cost_per_counted_unit, 'costPerUnit', t),
      fullWidth: true,
    },
  ];
}

function costMetadataItemsLoaded(
  t: TFunction,
  cost: AisleCostRow | InventoryCostRow,
  prefix: string
): AnalyticsMetadataItem[] {
  return [
    { id: `${prefix}-total-cost`, label: t('analyticsDashboard.costs.totalCost'), value: formatCostCell(cost.total_cost, 'cost', t) },
    {
      id: `${prefix}-total-qty`,
      label: t('analyticsDashboard.costs.totalQuantity'),
      value: formatCostCell(cost.total_counted_quantity, 'quantity', t),
    },
    {
      id: `${prefix}-cpu`,
      label: t('analyticsDashboard.costs.costPerUnit'),
      value: formatCostCell(cost.cost_per_counted_unit, 'costPerUnit', t),
      fullWidth: true,
    },
  ];
}

function compareActions(
  t: TFunction,
  inventoryId: string,
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>,
  options: { aisleId?: string; compareLabelKey: string; testIdPrefix: string }
): AnalyticsEntityAction[] {
  const eligibility = getCompareEligibility(inventoryProcessingModeById.get(inventoryId));
  const actions: AnalyticsEntityAction[] = [];
  if (eligibility.allowed) {
    actions.push({
      id: 'compare',
      label: t(options.compareLabelKey),
      href: pathToInventoryAnalyticsCompareMany(
        inventoryId,
        options.aisleId ? { aisleId: options.aisleId } : undefined
      ),
      testId: `${options.testIdPrefix}-compare-${options.aisleId ?? inventoryId}`,
    });
  } else {
    const tooltip = t(compareEligibilityTooltipKey(eligibility.reason));
    if (tooltip) {
      actions.push({
        id: 'compare-disabled',
        label: t(options.compareLabelKey),
        disabled: true,
        tooltip,
        testId: `${options.testIdPrefix}-compare-${options.aisleId ?? inventoryId}`,
      });
    }
  }
  return actions;
}

export function buildInventoryRankingCardItems(options: {
  rows: readonly InventoryPerformanceRow[];
  costByInventory: ReadonlyMap<string, InventoryCostRow>;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenInventoryDrilldown: (inventoryId: string) => void;
  t: TFunction;
}): AnalyticsEntityRankingCardItem[] {
  const { rows, costByInventory, isCostLoading, inventoryProcessingModeById, onOpenInventoryDrilldown, t } = options;

  return rows.map((row) => {
    const cost = costByInventory.get(row.inventory_id);
    const metadata: AnalyticsMetadataItem[] = [
      {
        id: 'auto-accept',
        label: t('analytics.column_auto_accept'),
        value: formatPct(row.auto_acceptance_rate),
      },
      ...costMetadataItems(t, cost, isCostLoading, row.inventory_id),
      {
        id: 'avg-processing',
        label: t('analytics.column_avg_processing'),
        value: formatAvgProcessingMinutes(row.average_processing_time_minutes, null),
        fullWidth: true,
      },
    ];

    return {
      id: row.inventory_id,
      title: row.inventory_name,
      metadata,
      testId: `analytics-inventory-card-${row.inventory_id}`,
      actions: [
        {
          id: 'view-detail',
          label: t('analyticsDashboard.inventories.viewDetail'),
          href: pathToInventory(row.inventory_id),
          testId: `inventory-view-detail-${row.inventory_id}`,
        },
        {
          id: 'analytics',
          label: t('analyticsDashboard.inventories.openAnalytics'),
          onClick: () => onOpenInventoryDrilldown(row.inventory_id),
          testId: `inventory-drilldown-${row.inventory_id}`,
        },
        ...compareActions(t, row.inventory_id, inventoryProcessingModeById, {
          compareLabelKey: 'analyticsDashboard.inventories.compareRuns',
          testIdPrefix: 'inventory',
        }),
      ],
    };
  });
}

export function buildAisleRankingCardItems(options: {
  rows: readonly AisleIssueRow[];
  costByAisle: ReadonlyMap<string, AisleCostRow>;
  isCostLoading: boolean;
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
  t: TFunction;
}): AnalyticsEntityRankingCardItem[] {
  const { rows, costByAisle, isCostLoading, inventoryProcessingModeById, onOpenAisleDrilldown, t } = options;

  return rows.map((row) => {
    const entityKey = buildAisleEntityKey(row.inventory_id, row.aisle_id);
    const cost = costByAisle.get(entityKey);
    const reviewLine = [
      t('analyticsDashboard.visual.attentionReviewRequired', { count: row.needs_review_count }),
      row.most_common_issue
        ? t('analyticsDashboard.visual.attentionPrimaryIssue', { issue: row.most_common_issue })
        : null,
    ]
      .filter(Boolean)
      .join(' · ');

    return {
      id: entityKey,
      title: row.aisle_code,
      subtitle: [row.inventory_name, reviewLine].filter(Boolean).join(' · '),
      metadata: costMetadataItems(t, cost, isCostLoading, entityKey),
      testId: `analytics-aisle-card-${row.aisle_id}`,
      actions: [
        {
          id: 'view-positions',
          label: t('analyticsDashboard.aisles.viewPositions'),
          href: pathToAislePositions(row.inventory_id, row.aisle_id),
          testId: `aisle-view-positions-${row.aisle_id}`,
        },
        {
          id: 'analytics',
          label: t('analyticsDashboard.aisles.openAnalytics'),
          onClick: () => onOpenAisleDrilldown(row.inventory_id, row.aisle_id),
          testId: `aisle-drilldown-${row.aisle_id}`,
        },
        ...compareActions(t, row.inventory_id, inventoryProcessingModeById, {
          aisleId: row.aisle_id,
          compareLabelKey: 'analyticsDashboard.aisles.compareRuns',
          testIdPrefix: 'aisle',
        }),
      ],
    };
  });
}

export function buildCostInventoryRankingCardItems(options: {
  rows: readonly InventoryCostRow[];
  onOpenInventoryDrilldown: (inventoryId: string) => void;
  t: TFunction;
}): AnalyticsEntityRankingCardItem[] {
  const { rows, onOpenInventoryDrilldown, t } = options;

  return rows.map((row) => ({
    id: row.inventory_id,
    title: row.inventory_name ?? row.inventory_id,
    metadata: costMetadataItemsLoaded(t, row, row.inventory_id),
    testId: `analytics-cost-inventory-card-${row.inventory_id}`,
    actions: [
      {
        id: 'analytics',
        label: t('analyticsDashboard.drilldown.openAnalytics'),
        onClick: () => onOpenInventoryDrilldown(row.inventory_id),
        testId: `cost-drilldown-inventory-${row.inventory_id}`,
      },
    ],
  }));
}

export function buildCostAisleRankingCardItems(options: {
  rows: readonly AisleCostRow[];
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
  t: TFunction;
}): AnalyticsEntityRankingCardItem[] {
  const { rows, onOpenAisleDrilldown, t } = options;

  return rows.map((row) => {
    const entityKey = buildAisleEntityKey(row.inventory_id, row.aisle_id);
    return {
      id: entityKey,
      title: `${row.aisle_code ?? row.aisle_id} · ${row.inventory_name ?? row.inventory_id}`,
      metadata: costMetadataItemsLoaded(t, row, entityKey),
      testId: `analytics-cost-aisle-card-${row.aisle_id}`,
      actions: [
        {
          id: 'analytics',
          label: t('analyticsDashboard.drilldown.openAnalytics'),
          onClick: () => onOpenAisleDrilldown(row.inventory_id, row.aisle_id),
          testId: `cost-drilldown-aisle-${row.aisle_id}`,
        },
      ],
    };
  });
}

export function buildQualityAisleAttentionRankingItems(options: {
  rows: readonly AisleIssueRow[];
  inventoryProcessingModeById: ReadonlyMap<string, string | undefined>;
  onOpenAisleDrilldown: (inventoryId: string, aisleId: string) => void;
  t: TFunction;
}): AnalyticsEntityRankingCardItem[] {
  const { rows, inventoryProcessingModeById, onOpenAisleDrilldown, t } = options;

  return rows.map((row) => {
    const entityKey = buildAisleEntityKey(row.inventory_id, row.aisle_id);
    const subtitle = [
      t('analyticsDashboard.quality.aislePending', { count: row.needs_review_count }),
      row.most_common_issue
        ? t('analyticsDashboard.visual.attentionPrimaryIssue', { issue: row.most_common_issue })
        : null,
    ]
      .filter(Boolean)
      .join(' · ');

    return {
      id: entityKey,
      title: `${row.aisle_code} · ${row.inventory_name}`,
      subtitle,
      metadata: [],
      testId: `analytics-quality-aisle-${row.aisle_id}`,
      actions: [
        {
          id: 'analytics',
          label: t('analyticsDashboard.quality.viewInAnalytics'),
          onClick: () => onOpenAisleDrilldown(row.inventory_id, row.aisle_id),
          testId: `quality-aisle-drilldown-${row.aisle_id}`,
        },
        ...compareActions(t, row.inventory_id, inventoryProcessingModeById, {
          aisleId: row.aisle_id,
          compareLabelKey: 'analyticsDashboard.quality.compareRuns',
          testIdPrefix: 'quality-aisle',
        }),
      ],
    };
  });
}

function pctLabel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)} %`;
}

export function buildProviderComparisonCardItems(
  rows: readonly ProviderRow[],
  t: TFunction
): AnalyticsEntityRankingCardItem[] {
  return rows.map((row, idx) => ({
    id: `${row.provider_name ?? ''}-${row.model_name ?? ''}-${idx}`,
    title: `${row.provider_name ?? t('observability.metrics.unknownId')} / ${row.model_name ?? t('observability.metrics.unknownId')}`,
    metadata: [
      { id: 'runs', label: t('observability.metrics.colRuns'), value: row.runs_total },
      { id: 'succeeded', label: t('observability.metrics.colSucceeded'), value: row.runs_succeeded },
      { id: 'failed', label: t('observability.metrics.colFailed'), value: row.runs_failed },
      {
        id: 'failure-rate',
        label: t('analyticsDashboard.providers.observedFailureRate'),
        value: pctLabel(row.failure_rate),
      },
    ],
    testId: `analytics-provider-card-${idx}`,
    actions: [],
  }));
}
