/**
 * Aisle list rows: presentation models for the table plus separate operational context for actions.
 */

import type { Aisle } from '../../../api/types';
import type { StatusBadgeSemantic } from '../../../components/ui/StatusBadge';
import i18n from '../../../i18n';
import { formatDate } from '../../../utils/formatDate';
import { getAisleStatusLabel, aisleStatusToBadgeSemantic } from '../../../utils/aisleStatus';
import { jobStatusToBadgeSemantic } from '../../../utils/jobStatus';
import { deriveAisleEffectiveDisplayState } from '../../../utils/deriveJobDisplayState';
import { getJobProcessingStatusLabel } from '../../../utils/jobFinalizationLabels';
import { toReferenceUsageRowViewModel, type ReferenceUsageRowViewModel } from './referenceUsageViewModel';
import type { AisleProcessMenuInput } from './processAisleMenuState';
import { getLatestRunFromAisleListItem } from './aisleListRunSource';

/** Snapshot of the latest run as shown in the inventory aisle grid (status + provider/model labels). */
export interface LatestRunSnapshotViewModel {
  statusLabel: string;
  statusSemantic: StatusBadgeSemantic;
  providerDisplay: string;
  modelDisplay: string;
  /** Raw API values for client-side column sort (not localized). */
  jobStatusRaw: string;
  providerRaw: string;
  modelRaw: string;
}

/**
 * Table cells only — labels, semantics, formatted values, and row identity for links/navigation.
 * Workflow/ops data (`processMenuAisle`, `observabilityInitialRunId`) stays on `AisleInventoryRowActionContext`.
 */
export interface AisleInventoryRowPresentation {
  id: string;
  code: string;
  /** Aisle `client_supplier_id` when present (supplier-linked prompt context). */
  clientSupplierId: string | null;
  aisleStatusLabel: string;
  aisleStatusSemantic: StatusBadgeSemantic;
  assetsCount: number | undefined;
  assetsCountDisplay: string | number;
  positionsCount: number | undefined;
  positionsCountDisplay: string | number;
  pendingReviewCount: number | undefined;
  pendingReviewDisplay: string | number;
  lastUpdatedDisplay: string;
  /** ISO timestamp for client-side sort (same source as display). */
  lastUpdatedSortKey: string | null;
  latestRun: LatestRunSnapshotViewModel | null;
  referenceUsage: ReferenceUsageRowViewModel | null;
}

/**
 * Data required for row actions (process menu, observability). Not used for rendering badges/text cells.
 */
export interface AisleInventoryRowActionContext {
  processMenuAisle: AisleProcessMenuInput;
  /** Backend run identifier for log/observability surfaces (v3 job id). */
  observabilityInitialRunId: string | null;
}

export interface AisleInventoryTableRow {
  presentation: AisleInventoryRowPresentation;
  action: AisleInventoryRowActionContext;
}

export function toAisleInventoryRowPresentation(aisle: Aisle, emptyLabel: string): AisleInventoryRowPresentation {
  const run = getLatestRunFromAisleListItem(aisle);
  const effectiveDisplay = deriveAisleEffectiveDisplayState(aisle, run);
  const latestRun: LatestRunSnapshotViewModel | null = run
    ? {
        statusLabel: getJobProcessingStatusLabel(run, i18n.t.bind(i18n)),
        statusSemantic: (() => {
          if (effectiveDisplay === 'failed') return 'error';
          if (effectiveDisplay === 'completed') return 'success';
          if (effectiveDisplay === 'completed_with_finalization_warning') return 'warning';
          if (effectiveDisplay === 'canceled') return 'warning';
          return jobStatusToBadgeSemantic(run.status);
        })(),
        providerDisplay: run.provider_name ? String(run.provider_name) : emptyLabel,
        modelDisplay: run.model_name ? String(run.model_name) : emptyLabel,
        jobStatusRaw: String(run.status),
        providerRaw: run.provider_name ? String(run.provider_name) : '',
        modelRaw: run.model_name ? String(run.model_name) : '',
      }
    : null;

  const aisleDisplay = deriveAisleEffectiveDisplayState(aisle, run);
  const aisleStatusLabel =
    aisleDisplay === 'processing' && run
      ? getJobProcessingStatusLabel(run, i18n.t.bind(i18n))
      : getAisleStatusLabel(String(aisle.status));
  const aisleStatusSemantic =
    aisleDisplay === 'failed'
      ? 'error'
      : aisleDisplay === 'completed_with_finalization_warning'
        ? 'warning'
        : aisleDisplay === 'completed'
          ? 'success'
          : aisleStatusToBadgeSemantic(String(aisle.status));

  return {
    id: aisle.id,
    code: aisle.code,
    clientSupplierId: aisle.client_supplier_id ?? null,
    aisleStatusLabel,
    aisleStatusSemantic,
    assetsCount: aisle.assets_count,
    assetsCountDisplay:
      typeof aisle.assets_count === 'number' ? aisle.assets_count : emptyLabel,
    positionsCount: aisle.positions_count,
    positionsCountDisplay:
      typeof aisle.positions_count === 'number' ? aisle.positions_count : emptyLabel,
    pendingReviewCount: aisle.pending_review_positions_count,
    pendingReviewDisplay:
      typeof aisle.pending_review_positions_count === 'number'
        ? aisle.pending_review_positions_count
        : emptyLabel,
    lastUpdatedDisplay: formatDate(aisle.last_activity_at ?? aisle.updated_at),
    lastUpdatedSortKey: (aisle.last_activity_at ?? aisle.updated_at ?? null) as string | null,
    latestRun,
    referenceUsage: toReferenceUsageRowViewModel(aisle),
  };
}

export function toAisleInventoryRowActionContext(aisle: Aisle): AisleInventoryRowActionContext {
  const run = getLatestRunFromAisleListItem(aisle);
  return {
    processMenuAisle: {
      id: aisle.id,
      status: aisle.status,
      assets_count: aisle.assets_count,
    },
    observabilityInitialRunId: run?.id ?? null,
  };
}

export function toAisleInventoryTableRow(aisle: Aisle, emptyLabel: string): AisleInventoryTableRow {
  return {
    presentation: toAisleInventoryRowPresentation(aisle, emptyLabel),
    action: toAisleInventoryRowActionContext(aisle),
  };
}

export function toAisleInventoryTableRows(aisles: Aisle[], emptyLabel: string): AisleInventoryTableRow[] {
  return aisles.map((a) => toAisleInventoryTableRow(a, emptyLabel));
}
