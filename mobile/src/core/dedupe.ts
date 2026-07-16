/**
 * Deduplicate photo lists by stable asset identity.
 */
export interface DedupablePhoto {
  readonly assetId: string;
  readonly uri?: string;
}

/**
 * Merge `incoming` into `existing`, keeping the first occurrence of each assetId.
 * Falls back to uri only when assetId is missing (should not happen with requireAssetId).
 */
export function mergeUniqueByAssetId<T extends DedupablePhoto>(
  existing: readonly T[],
  incoming: readonly T[],
): T[] {
  const seen = new Set<string>();
  const out: T[] = [];

  const keyOf = (p: T): string => {
    const id = (p.assetId || '').trim();
    if (id) {
      return `id:${id}`;
    }
    return `uri:${(p.uri || '').trim()}`;
  };

  for (const p of [...existing, ...incoming]) {
    const key = keyOf(p);
    if (!key || key === 'id:' || key === 'uri:') {
      continue;
    }
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(p);
  }
  return out;
}

/** Upsert by assetId: replace existing entry or append. */
export function upsertByAssetId<T extends DedupablePhoto>(
  existing: readonly T[],
  item: T,
): T[] {
  const idx = existing.findIndex((p) => p.assetId === item.assetId);
  if (idx < 0) {
    return [...existing, item];
  }
  const next = existing.slice();
  next[idx] = item;
  return next;
}
