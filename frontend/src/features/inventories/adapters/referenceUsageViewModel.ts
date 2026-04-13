/**
 * Maps aisle + latest run reference payload into a compact table cell view model.
 * Keeps UI off raw `latest_job.reference_usage` branching.
 */

import type { Aisle } from '../../../api/types';
import type { StatusBadgeSemantic } from '../../../components/ui/StatusBadge';
import i18n from '../../../i18n';

export interface ReferenceUsageRowViewModel {
  label: string;
  detail?: string;
  semantic: StatusBadgeSemantic;
}

export function toReferenceUsageRowViewModel(aisle: Aisle): ReferenceUsageRowViewModel | null {
  if (!aisle.latest_job) return null;

  const usage = aisle.latest_job.reference_usage;
  if (!usage) {
    return ['queued', 'running'].includes(String(aisle.latest_job.status).toLowerCase())
      ? { label: i18n.t('aisle.reference_usage.pending_run_summary'), semantic: 'neutral' }
      : { label: i18n.t('aisle.reference_usage.summary_unavailable'), semantic: 'neutral' };
  }

  const preparedLabel =
    usage.resolved_count === 1
      ? i18n.t('aisle.reference_usage.prepared_one')
      : i18n.t('aisle.reference_usage.prepared_many', { count: usage.resolved_count });
  const sentLabel =
    usage.provider_consumed_count === 1
      ? i18n.t('aisle.reference_usage.sent_one')
      : i18n.t('aisle.reference_usage.sent_many', { count: usage.provider_consumed_count });

  if (usage.resolution_error) {
    return {
      label: i18n.t('aisle.reference_usage.reference_setup_failed'),
      detail: i18n.t('aisle.reference_usage.setup_failed_detail', { prepared: preparedLabel }),
      semantic: 'error',
    };
  }

  if (usage.provider_consumed) {
    return {
      label: sentLabel,
      detail: preparedLabel,
      semantic: 'success',
    };
  }

  if (usage.resolved) {
    return {
      label: i18n.t('aisle.reference_usage.references_not_sent'),
      detail: preparedLabel,
      semantic: 'warning',
    };
  }

  return {
    label: i18n.t('aisle.reference_usage.processed_without_references'),
    semantic: 'neutral',
  };
}
