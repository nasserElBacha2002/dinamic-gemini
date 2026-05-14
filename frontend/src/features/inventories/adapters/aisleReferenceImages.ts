/**
 * Selects supplier reference images for the aisle visual references drawer (and similar UIs).
 *
 * If the latest run declares `reference_ids` and those IDs exist in the supplier catalog,
 * return that intersection first because it best represents the references used by the run.
 *
 * If no run references can be matched, fall back to the full supplier catalog because the
 * drawer is also used as a read-only view of the visual references configured for the aisle's
 * supplier (not necessarily only the exact files consumed in a single run).
 */

import type { Aisle, SupplierReferenceImage } from '../../../api/types';
import { getLatestRunFromAisleListItem } from './aisleListRunSource';

export function pickSupplierReferenceImagesForAisle(
  aisle: Aisle,
  supplierCatalog: SupplierReferenceImage[] | undefined
): SupplierReferenceImage[] {
  if (!supplierCatalog?.length) return [];
  const run = getLatestRunFromAisleListItem(aisle);
  const rawIds = run?.reference_usage?.reference_ids ?? [];
  const ids = rawIds.filter((x): x is string => typeof x === 'string' && x.trim() !== '');
  if (ids.length > 0) {
    const idSet = new Set(ids);
    const matched = supplierCatalog.filter((img) => idSet.has(img.id));
    if (matched.length > 0) return matched;
  }
  return supplierCatalog;
}
