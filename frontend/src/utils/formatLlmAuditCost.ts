/**
 * Formatting helpers for LLM cost snapshots in observability / auditability (Phase H5).
 */

const ES_AR = 'es-AR';

function parseDecimalString(value: string | null | undefined): number | null {
  if (value == null) return null;
  const t = String(value).trim();
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function formatAuditTokenCount(value: number | null | undefined, notReported: string): string {
  if (value == null || Number.isNaN(value)) return notReported;
  return new Intl.NumberFormat(ES_AR, { maximumFractionDigits: 0 }).format(value);
}

/** Format a monetary amount for LLM micro-costs (avoids rounding tiny totals to 0.00). */
export function formatAuditLlmMoney(amount: number, currency: string, notReported: string): string {
  if (!Number.isFinite(amount)) return notReported;
  const abs = Math.abs(amount);
  const minFrac = abs > 0 && abs < 0.01 ? 6 : 2;
  const maxFrac = abs > 0 && abs < 0.01 ? 6 : 4;
  try {
    return new Intl.NumberFormat(ES_AR, {
      style: 'currency',
      currency: currency.length === 3 ? currency : 'USD',
      minimumFractionDigits: minFrac,
      maximumFractionDigits: maxFrac,
    }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

export function formatAuditCostFromApiString(
  value: string | null | undefined,
  currency: string | null | undefined,
  notReported: string
): string {
  const n = parseDecimalString(value);
  if (n == null) return notReported;
  return formatAuditLlmMoney(n, (currency ?? 'USD').trim() || 'USD', notReported);
}
