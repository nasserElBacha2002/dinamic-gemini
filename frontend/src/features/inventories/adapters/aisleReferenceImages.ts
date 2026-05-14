/**
 * Pick supplier reference images to show for an inventory aisle row.
 * When the latest job lists `reference_ids`, prefer those that exist in the supplier catalog;
 * otherwise show the full supplier catalog (caller typically slices for display).
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
