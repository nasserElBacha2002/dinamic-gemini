/**
 * Flattened aisle list row for inventory screens — execution summary and counts without raw job DTOs in JSX.
 */

import type { Aisle } from '../../../api/types';
import type { StatusBadgeSemantic } from '../../../components/ui/StatusBadge';
import { formatDate } from '../../../utils/formatDate';
import { getAisleStatusLabel, aisleStatusToBadgeSemantic } from '../../../utils/aisleStatus';
import { getJobStatusLabel, jobStatusToBadgeSemantic } from '../../../utils/jobStatus';
import { toReferenceUsageRowViewModel, type ReferenceUsageRowViewModel } from './referenceUsageViewModel';
import type { AisleProcessMenuInput } from './processAisleMenuState';

export interface AisleExecutionSummaryViewModel {
  jobStatusLabel: string;
  jobStatusSemantic: StatusBadgeSemantic;
  providerDisplay: string;
  modelDisplay: string;
}

export interface AisleInventoryRowViewModel {
  id: string;
  code: string;
  aisleStatusLabel: string;
  aisleStatusSemantic: StatusBadgeSemantic;
  assetsCount: number | undefined;
  assetsCountDisplay: string | number;
  positionsCount: number | undefined;
  positionsCountDisplay: string | number;
  pendingReviewCount: number | undefined;
  pendingReviewDisplay: string | number;
  lastUpdatedDisplay: string;
  execution: AisleExecutionSummaryViewModel | null;
  referenceUsage: ReferenceUsageRowViewModel | null;
  executionJobId: string | null;
  /** Subset of aisle fields for process / upload menu gating */
  processMenuAisle: AisleProcessMenuInput;
}

export function toAisleInventoryRowViewModel(
  aisle: Aisle,
  emptyLabel: string
): AisleInventoryRowViewModel {
  const job = aisle.latest_job;
  const execution: AisleExecutionSummaryViewModel | null = job
    ? {
        jobStatusLabel: getJobStatusLabel(job.status),
        jobStatusSemantic: jobStatusToBadgeSemantic(job.status),
        providerDisplay: job.provider_name ? String(job.provider_name) : emptyLabel,
        modelDisplay: job.model_name ? String(job.model_name) : emptyLabel,
      }
    : null;

  return {
    id: aisle.id,
    code: aisle.code,
    aisleStatusLabel: getAisleStatusLabel(String(aisle.status)),
    aisleStatusSemantic: aisleStatusToBadgeSemantic(String(aisle.status)),
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
    execution,
    referenceUsage: toReferenceUsageRowViewModel(aisle),
    executionJobId: job?.id ?? null,
    processMenuAisle: {
      id: aisle.id,
      status: aisle.status,
      assets_count: aisle.assets_count,
    },
  };
}

export function toAisleInventoryRowViewModels(
  aisles: Aisle[],
  emptyLabel: string
): AisleInventoryRowViewModel[] {
  return aisles.map((a) => toAisleInventoryRowViewModel(a, emptyLabel));
}
