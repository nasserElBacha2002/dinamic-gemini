/**
 * User-facing labels for job/finalization processing states (Spanish primary via i18n).
 */

import type { TFunction } from 'i18next';
import type { JobLikeForDisplay } from './deriveJobDisplayState';
import { deriveEffectiveJobDisplayState } from './deriveJobDisplayState';

function norm(value: string | null | undefined): string {
  return String(value ?? '').trim().toLowerCase();
}

export function getJobProcessingStatusLabel(job: JobLikeForDisplay | null | undefined, t: TFunction): string {
  const display = deriveEffectiveJobDisplayState(job);
  if (display === 'failed') {
    const step = norm(job?.current_finalization_step);
    const code = norm(job?.finalization_error_code ?? job?.failure_code);
    if (step === 'persist_domain_results' || code === 'domain_persistence_failed') {
      return t('jobs.finalization.error_persist_domain');
    }
    if (step === 'publish_artifacts' || code.includes('artifact')) {
      return t('jobs.finalization.error_publish_artifacts');
    }
    if (code === 'stale_job' || code === 'worker_stale') {
      return t('jobs.finalization.error_worker_stale');
    }
    return t('jobs.finalization.failed_generic');
  }
  if (display === 'canceled') return t('jobs.finalization.canceled');
  if (display === 'completed_with_finalization_warning') {
    return t('jobs.finalization.completed_reconciliation_pending');
  }
  if (display === 'completed') return t('jobs.finalization.completed');
  const status = norm(job?.status);
  const step = norm(job?.current_finalization_step);
  if (status === 'running' && step === 'persist_domain_results') {
    return t('jobs.finalization.running_persist');
  }
  if (status === 'running' && step === 'publish_artifacts') {
    return t('jobs.finalization.running_publish');
  }
  if (status === 'running' && step === 'terminalize_job') {
    return t('jobs.finalization.running_terminalize');
  }
  return t('jobs.finalization.processing');
}

export function normalizeExecutionLogEventMessage(message: string): string {
  const m = message.trim();
  if (m === 'job.succeeded') return 'provider_pipeline.completed';
  return m;
}
