import type {
  CaptureSessionGroupSummaryResponse,
  CaptureSessionItemResponse,
} from '../../../types/captureSession';

/**
 * G6 **UI precheck only** (Import Session detail payload).
 *
 * Session ``items[]`` can lag G5 persistence or omit linkage while assets already exist on the aisle.
 * The **canonical** materialization / preview state is always the backend:
 * ``POST /inventories/{id}/capture-sessions/{session_id}/groups/{group_id}/preview`` (and materialize).
 * Never use this helper as the sole authority for business rules—only to reduce misleading clicks.
 */

/** @deprecated Use ``heuristicDetailItemsImplyNoLinkedSourceAssetForImportedGroupItems`` (same behavior). */
export function groupHasMaterializedAssetForGroup(
  groupId: string,
  items: CaptureSessionItemResponse[]
): boolean {
  return !heuristicDetailItemsImplyNoLinkedSourceAssetForImportedGroupItems(groupId, items);
}

/**
 * True when detail items show at least one **imported** row for the group **and** every such row
 * lacks ``linked_source_asset_id``. If there are no rows for the group in ``items``, returns false
 * (no local evidence → do not block the preview CTA on materialization heuristics).
 */
export function heuristicDetailItemsImplyNoLinkedSourceAssetForImportedGroupItems(
  groupId: string,
  items: CaptureSessionItemResponse[]
): boolean {
  const gid = (groupId || '').trim();
  if (!gid) return true;
  const groupItems = items.filter((i) => (i.group_id ?? '').trim() === gid);
  if (groupItems.length === 0) {
    return false;
  }
  const imported = groupItems.filter((i) => i.import_status === 'imported');
  if (imported.length === 0) {
    return false;
  }
  return imported.every((i) => !(i.linked_source_asset_id ?? '').trim());
}

/** i18n key when the preview CTA should stay disabled based on **heuristic** session detail only. */
export function heuristicGroupPreviewCtaBlockedReasonKey(
  group: CaptureSessionGroupSummaryResponse,
  items: CaptureSessionItemResponse[]
): string | null {
  if ((group.assignment_status ?? 'unassigned') === 'unassigned') {
    return 'ingestion_sessions.detail.grouping_preview_disabled_assign';
  }
  const mat = group.materialization_state;
  if (mat === 'materialized' || mat === 'partially_materialized') {
    return null;
  }
  if (heuristicDetailItemsImplyNoLinkedSourceAssetForImportedGroupItems(group.group_id, items)) {
    return 'ingestion_sessions.detail.grouping_preview_disabled_materialize';
  }
  return null;
}

/** @deprecated Use ``heuristicGroupPreviewCtaBlockedReasonKey``. */
export function groupPreviewUnavailableReasonKey(
  group: CaptureSessionGroupSummaryResponse,
  items: CaptureSessionItemResponse[]
): string | null {
  return heuristicGroupPreviewCtaBlockedReasonKey(group, items);
}
