export const CHART_TOP_N = 5;

/** Top aisles shown on the Summary tab attention panel (progressive disclosure). */
export const SUMMARY_ATTENTION_TOP_N = 3;

/** Top aisles ranked on the Quality tab. */
export const QUALITY_AISLE_ATTENTION_TOP_N = 5;

export interface BarChartDatum {
  id: string;
  label: string;
  value: number;
  displayValue: string;
}

export interface SegmentDatum {
  id: string;
  label: string;
  value: number;
  pct: number;
}

export function rankTopN<T>(options: {
  items: readonly T[];
  getValue: (item: T) => number | null | undefined;
  getLabel: (item: T) => string;
  getId: (item: T, index: number) => string;
  formatDisplay: (value: number, item: T) => string;
  limit?: number;
  direction?: 'asc' | 'desc';
  includeZero?: boolean;
}): BarChartDatum[] {
  const {
    items,
    getValue,
    getLabel,
    getId,
    formatDisplay,
    limit = CHART_TOP_N,
    direction = 'desc',
    includeZero = false,
  } = options;

  const ranked = items
    .map((item, index) => {
      const value = getValue(item);
      if (value == null || !Number.isFinite(value)) return null;
      if (!includeZero && value <= 0) return null;
      return {
        id: getId(item, index),
        label: getLabel(item),
        value,
        displayValue: formatDisplay(value, item),
      };
    })
    .filter((x): x is BarChartDatum => x != null)
    .sort((a, b) => (direction === 'asc' ? a.value - b.value : b.value - a.value))
    .slice(0, limit);

  return ranked;
}

/** @deprecated Prefer rankTopN for new builders. */
export function topByValue<T>(
  items: readonly T[],
  getValue: (item: T) => number | null | undefined,
  getLabel: (item: T) => string,
  getId: (item: T, index: number) => string,
  formatDisplay: (value: number) => string,
  limit = CHART_TOP_N
): BarChartDatum[] {
  return rankTopN({
    items,
    getValue,
    getLabel,
    getId,
    formatDisplay: (value) => formatDisplay(value),
    limit,
  });
}
