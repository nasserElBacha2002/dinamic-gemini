import type {
  CaptureSessionGroupSummaryResponse,
  CaptureSessionItemResponse,
} from '../../../types/captureSession';

/** True when at least one session item in this temporal group has a linked aisle ``SourceAsset`` (G5+). */
export function groupHasMaterializedAssetForGroup(
  groupId: string,
  items: CaptureSessionItemResponse[]
): boolean {
  const gid = (groupId || '').trim();
  if (!gid) return false;
  return items.some(
    (i) => (i.group_id ?? '').trim() === gid && !!(i.linked_source_asset_id ?? '').trim()
  );
}

/** i18n key for why preview is disabled in the UI, or null when preview may be invoked. */
export function groupPreviewUnavailableReasonKey(
  group: CaptureSessionGroupSummaryResponse,
  items: CaptureSessionItemResponse[]
): string | null {
  if ((group.assignment_status ?? 'unassigned') === 'unassigned') {
    return 'ingestion_sessions.detail.grouping_preview_disabled_assign';
  }
  if (!groupHasMaterializedAssetForGroup(group.group_id, items)) {
    return 'ingestion_sessions.detail.grouping_preview_disabled_materialize';
  }
  return null;
}
