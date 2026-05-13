import type { TFunction } from 'i18next';
import type { BenchmarkRunCompareSide, JobSummary, LlmCostSnapshot } from '../../../api/types';
import { formatExecutionDurationHuman } from '../../../utils/benchmarkExecutionTime';

export function userFacingCaptureNote(note: string, t: TFunction): string {
  if (note === 'provider_usage_missing') {
    return t('compare.llm_cost_note.provider_usage_missing');
  }
  if (note === 'pricing_entry_missing') {
    return t('compare.llm_cost_note.pricing_entry_missing');
  }
  if (note === 'pricing_present_but_no_billable_dimensions') {
    return t('compare.llm_cost_note.pricing_present_but_no_billable_dimensions');
  }
  if (note.startsWith('billable_dimension_not_priced:')) {
    const dimension = note.slice('billable_dimension_not_priced:'.length);
    return t('compare.llm_cost_note.billable_dimension_not_priced', { dimension });
  }
  if (note.startsWith('usage_dimension_ambiguous:')) {
    const dimension = note.slice('usage_dimension_ambiguous:'.length);
    return t('compare.llm_cost_note.usage_dimension_ambiguous', { dimension });
  }
  return note;
}

export function formatCostDisplay(
  run: {
    model_name?: string | null;
    llm_cost_snapshot?: Partial<LlmCostSnapshot> | null;
  },
  t: TFunction
): {
  value: string;
  details: string | null;
} {
  const snap = run.llm_cost_snapshot;
  if (!snap) {
    return {
      value: t('compare.llm_cost_display.no_snapshot'),
      details: null,
    };
  }
  const total = snap.computed_cost?.total_cost?.trim();
  const currency = snap.computed_cost?.currency?.trim() || snap.billing_currency?.trim();
  const statusKey = snap.capture_status ?? 'unavailable';
  const statusLabel = t(`compare.llm_cost_status.${statusKey}`, {
    defaultValue: t('compare.llm_cost_status.unavailable'),
  });
  const notes = Array.isArray(snap.capture_notes) ? snap.capture_notes : [];
  const noteText = notes.map((n) => userFacingCaptureNote(n, t)).filter(Boolean);
  const machineReason = snap.computed_cost?.total_cost_unavailable_reason?.trim();
  const details = [statusLabel, ...noteText].join(' · ');
  if (!total) {
    let value: string;
    if (notes.includes('pricing_entry_missing') || machineReason === 'pricing_entry_missing') {
      value = t('compare.llm_cost_display.no_pricing_configured');
    } else if (notes.includes('provider_usage_missing') || machineReason === 'provider_usage_missing') {
      value = t('compare.llm_cost_display.usage_not_reported');
    } else {
      value = t('compare.llm_cost_display.not_computed');
    }
    const modelLabel = (run.model_name || snap.model || '').trim();
    const showDetails =
      noteText.length > 0 ||
      statusKey !== 'unavailable' ||
      Boolean(machineReason) ||
      Boolean(modelLabel);
    const detailsWithModel =
      modelLabel && !total
        ? `${details}${details ? ' · ' : ''}${t('compare.llm_cost_display.model_in_tooltip', { model: modelLabel })}`
        : details;
    return { value, details: showDetails ? detailsWithModel : null };
  }
  return { value: `${total} ${currency || ''}`.trim(), details };
}

export function runExecutionDisplay(
  run: Pick<BenchmarkRunCompareSide, 'execution_time_human' | 'execution_time_seconds'>,
  t: TFunction
): string {
  if (run.execution_time_human) {
    return run.execution_time_human;
  }
  if (run.execution_time_seconds != null) {
    return formatExecutionDurationHuman(run.execution_time_seconds);
  }
  return t('compare.execution_unavailable');
}

export function signedValue(value: number): string {
  if (value > 0) return `+${value}`;
  return String(value);
}

export function semanticColor(value: number, higherIsWorse: boolean): 'success.main' | 'error.main' | 'text.primary' {
  if (value === 0) return 'text.primary';
  if (higherIsWorse) return value > 0 ? 'error.main' : 'success.main';
  return value > 0 ? 'success.main' : 'error.main';
}

export function displayJobName(job: JobSummary): string {
  return `${job.id.slice(0, 8)}…`;
}

export function compareRunExecutionLabel(
  run: { execution_time_human?: string | null; execution_time_seconds?: number | null },
  t: TFunction
): string {
  if (run.execution_time_human) {
    return run.execution_time_human;
  }
  if (run.execution_time_seconds != null) {
    return formatExecutionDurationHuman(run.execution_time_seconds);
  }
  return t('compare.execution_unavailable');
}
