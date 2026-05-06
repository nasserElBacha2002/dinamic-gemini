import type { MergeResultItemResponse } from '../../../api/types';

export type MergeCandidateSummary = {
  groupCount: number;
  skuExamples: string[];
};

export type MergeResultsSummary = {
  groupCount: number;
  skuCount: number;
  skuExamples: string[];
};

// UI-only heuristic: repeated visible SKUs are a conservative signal that manual merge
// may be useful. This is intentionally lighter than the backend merge domain logic.
export function summarizeLikelyMergeCandidates(
  positions: Array<{ sku?: string | null }>
): MergeCandidateSummary {
  const counts = new Map<string, { label: string; count: number }>();
  for (const position of positions) {
    const rawSku = position.sku?.trim();
    if (!rawSku) continue;
    const key = rawSku.toLowerCase();
    const current = counts.get(key);
    if (current) {
      current.count += 1;
    } else {
      counts.set(key, { label: rawSku, count: 1 });
    }
  }
  const repeated = Array.from(counts.values())
    .filter((entry) => entry.count > 1)
    .map((entry) => entry.label);
  return {
    groupCount: repeated.length,
    skuExamples: repeated.slice(0, 3),
  };
}

export function summarizeMergeResults(results: MergeResultItemResponse[] | undefined): MergeResultsSummary | null {
  const consolidated = (results ?? []).filter((item) => item.normalized_label_ids.length > 1);
  if (consolidated.length === 0) return null;
  const skuLabels = consolidated
    .map((item) => item.sku?.trim())
    .filter((sku): sku is string => Boolean(sku));
  const uniqueSkuLabels = Array.from(new Set(skuLabels));
  return {
    groupCount: consolidated.length,
    skuCount: uniqueSkuLabels.length,
    skuExamples: uniqueSkuLabels.slice(0, 3),
  };
}
