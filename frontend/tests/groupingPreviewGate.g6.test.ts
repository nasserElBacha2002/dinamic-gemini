import { describe, it, expect } from 'vitest';
import {
  groupHasMaterializedAssetForGroup,
  groupPreviewUnavailableReasonKey,
} from '../src/features/ingestionSessions/utils/groupingPreviewGate';
import type {
  CaptureSessionGroupSummaryResponse,
  CaptureSessionItemResponse,
} from '../src/types/captureSession';

function group(overrides: Partial<CaptureSessionGroupSummaryResponse> = {}): CaptureSessionGroupSummaryResponse {
  return {
    group_id: 'g-1',
    group_index: 1,
    item_count: 1,
    start_time: '2026-01-01T00:00:00Z',
    end_time: '2026-01-01T01:00:00Z',
    algorithm_version: 'time_gap_v1',
    assignment_status: 'unassigned',
    assigned_aisle_id: null,
    assigned_at: null,
    ...overrides,
  };
}

function item(overrides: Partial<CaptureSessionItemResponse> = {}): CaptureSessionItemResponse {
  return {
    id: 'i-1',
    session_id: 's-1',
    staging_storage_key: 'k',
    import_status: 'imported',
    assignment_status: 'pending',
    updated_at: '2026-01-01T00:00:00Z',
    group_id: 'g-1',
    linked_source_asset_id: null,
    ...overrides,
  };
}

describe('groupingPreviewGate — G6', () => {
  it('disables preview for unassigned groups', () => {
    const reason = groupPreviewUnavailableReasonKey(group({ assignment_status: 'unassigned' }), []);
    expect(reason).toBe('ingestion_sessions.detail.grouping_preview_disabled_assign');
  });

  it('disables preview until at least one item has linked_source_asset_id', () => {
    const reason = groupPreviewUnavailableReasonKey(
      group({ assignment_status: 'assigned_existing', assigned_aisle_id: 'a-1' }),
      [item({ linked_source_asset_id: null })]
    );
    expect(reason).toBe('ingestion_sessions.detail.grouping_preview_disabled_materialize');
  });

  it('returns null when preview may run', () => {
    const reason = groupPreviewUnavailableReasonKey(
      group({ assignment_status: 'assigned_existing', assigned_aisle_id: 'a-1' }),
      [item({ linked_source_asset_id: 'asset-1' })]
    );
    expect(reason).toBeNull();
  });

  it('detects materialized items for the group', () => {
    expect(groupHasMaterializedAssetForGroup('g-1', [item({ group_id: 'g-1', linked_source_asset_id: 'x' })])).toBe(
      true
    );
    expect(groupHasMaterializedAssetForGroup('g-1', [item({ group_id: 'g-1', linked_source_asset_id: '' })])).toBe(
      false
    );
    expect(groupHasMaterializedAssetForGroup('g-1', [item({ group_id: 'g-2', linked_source_asset_id: 'x' })])).toBe(
      false
    );
  });
});
