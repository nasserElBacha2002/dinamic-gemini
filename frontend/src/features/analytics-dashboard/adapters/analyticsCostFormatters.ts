import type { TFunction } from 'i18next';

/** LLM snapshot amounts; backend does not expose a currency code — show neutral numeric values. */
function isValidNumber(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value);
}

export function formatLlmCostAmount(value: number | null | undefined): string {
  if (!isValidNumber(value)) {
    return '—';
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

export function formatCountedQuantity(value: number | null | undefined): string {
  if (!isValidNumber(value)) {
    return '—';
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function formatCostPerUnit(value: number | null | undefined): string {
  if (!isValidNumber(value)) {
    return '—';
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  });
}

export function formatExecutionSeconds(value: number | null | undefined): string {
  if (!isValidNumber(value)) {
    return '—';
  }
  if (value < 60) {
    return `${value.toFixed(1)} s`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return seconds > 0 ? `${minutes} min ${seconds} s` : `${minutes} min`;
}

export function formatMetricValue(
  value: number | null | undefined,
  kind: 'cost' | 'quantity' | 'costPerUnit' | 'integer' | 'duration'
): string {
  switch (kind) {
    case 'cost':
      return formatLlmCostAmount(value);
    case 'quantity':
      return formatCountedQuantity(value);
    case 'costPerUnit':
      return formatCostPerUnit(value);
    case 'duration':
      return formatExecutionSeconds(value);
    case 'integer':
    default:
      if (!isValidNumber(value)) return '—';
      return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
}

export function captureStatusLabel(status: string, t: TFunction): string {
  const key = `analyticsDashboard.costs.captureStatus.${status}`;
  const translated = t(key);
  return translated === key ? status : translated;
}
