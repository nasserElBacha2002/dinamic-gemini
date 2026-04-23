import '@testing-library/jest-dom/vitest';
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ImportSessionGroupingPanel from '../src/features/ingestionSessions/components/ImportSessionGroupingPanel';
import type { CaptureSessionItemResponse, CaptureSessionResponse } from '../src/types/captureSession';

const mockUseCaptureSessionGroups = vi.fn();
const mockUseComputeCaptureSessionGroups = vi.fn();
const mockUseAisleOptions = vi.fn();
const mockUseAssignCaptureSessionGroupToExistingAisle = vi.fn();
const mockUseCreateAisleFromCaptureSessionGroup = vi.fn();
const mockUseMaterializeCaptureSessionGroup = vi.fn();
const mockUsePreviewMaterializedCaptureSessionGroup = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (key === 'ingestion_sessions.detail.grouping_preview') return 'Preview';
      if (key === 'ingestion_sessions.detail.grouping_materialize') return 'Materialize';
      if (key === 'ingestion_sessions.detail.grouping_preview_disabled_materialize') {
        return 'Materialize this group before preview';
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_disabled_assign') {
        return 'Assign this group to an aisle first';
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_dialog_title') return 'Preview dialog';
      if (key === 'ingestion_sessions.detail.grouping_preview_trace_session' && options && 'id' in options) {
        return `Session: ${String(options.id)}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_meta') return 'Meta line';
      if (key === 'ingestion_sessions.detail.grouping_preview_summary') return 'Summary line';
      if (key === 'ingestion_sessions.detail.grouping_assign_dialog_cancel') return 'Close';
      if (key === 'ingestion_sessions.detail.grouping_preview_row_reason' && options && 'reason' in options) {
        return `Reason: ${String(options.reason)}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_row_status' && options && 'status' in options) {
        return `Status: ${String(options.status)}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_row_item' && options && 'id' in options) {
        return `Item: ${String(options.id)}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_row_asset' && options && 'id' in options) {
        return `Asset: ${String(options.id)}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_row_position' && options && 'id' in options) {
        return `Position: ${String(options.id)}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_preview_row_time' && options && 'time' in options) {
        return `Time: ${String(options.time)}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_title') return 'Grouping';
      if (key === 'ingestion_sessions.detail.grouping_compute') return 'Compute groups';
      if (key === 'ingestion_sessions.detail.grouping_hint_close') return 'Close hint';
      if (key === 'ingestion_sessions.detail.grouping_loading') return 'Loading';
      if (key === 'ingestion_sessions.detail.grouping_empty') return 'No groups';
      if (key.startsWith('ingestion_sessions.detail.')) return key;
      return key;
    },
  }),
}));

vi.mock('../src/features/ingestionSessions/hooks/useCaptureSessions', () => ({
  useCaptureSessionGroups: (...args: unknown[]) => mockUseCaptureSessionGroups(...args),
  useComputeCaptureSessionGroups: () => mockUseComputeCaptureSessionGroups(),
  useAisleOptions: (...args: unknown[]) => mockUseAisleOptions(...args),
  useAssignCaptureSessionGroupToExistingAisle: () => mockUseAssignCaptureSessionGroupToExistingAisle(),
  useCreateAisleFromCaptureSessionGroup: () => mockUseCreateAisleFromCaptureSessionGroup(),
  useMaterializeCaptureSessionGroup: () => mockUseMaterializeCaptureSessionGroup(),
  usePreviewMaterializedCaptureSessionGroup: () => mockUsePreviewMaterializedCaptureSessionGroup(),
}));

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function baseSession(overrides: Partial<CaptureSessionResponse> = {}): CaptureSessionResponse {
  return {
    id: 'sess-1',
    inventory_id: 'inv-1',
    aisle_id: null,
    status: 'ready_for_review',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    opened_at: null,
    closed_at: '2026-01-01T01:00:00Z',
    clock_offset_seconds: 0,
    ...overrides,
  };
}

describe('ImportSessionGroupingPanel — G6 preview CTA', () => {
  beforeEach(() => {
    mockUseCaptureSessionGroups.mockReset();
    mockUseComputeCaptureSessionGroups.mockReset();
    mockUseAisleOptions.mockReset();
    mockUseAssignCaptureSessionGroupToExistingAisle.mockReset();
    mockUseCreateAisleFromCaptureSessionGroup.mockReset();
    mockUseMaterializeCaptureSessionGroup.mockReset();
    mockUsePreviewMaterializedCaptureSessionGroup.mockReset();
    mockUseComputeCaptureSessionGroups.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseAisleOptions.mockReturnValue({
      data: { items: [{ id: 'aisle-1', code: 'A-01' }], page: 1, page_size: 200, total_items: 1, total_pages: 1 },
      isLoading: false,
      error: null,
    });
    mockUseAssignCaptureSessionGroupToExistingAisle.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseCreateAisleFromCaptureSessionGroup.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseMaterializeCaptureSessionGroup.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
      error: null,
    });
    mockUsePreviewMaterializedCaptureSessionGroup.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
  });

  it('disables Preview when the group is assigned but items have no linked_source_asset_id', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-01T00:00:00Z',
            end_time: '2026-01-01T00:05:00Z',
            algorithm_version: 'time_gap_v1',
            assignment_status: 'assigned_existing',
            assigned_aisle_id: 'aisle-1',
            assigned_at: '2026-01-01T00:10:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    const items: CaptureSessionItemResponse[] = [
      {
        id: 'item-1',
        session_id: 'sess-1',
        staging_storage_key: 'k',
        import_status: 'imported',
        assignment_status: 'pending',
        updated_at: '2026-01-01T00:00:00Z',
        group_id: 'g-1',
        linked_source_asset_id: null,
      },
    ];
    renderWithClient(
      <ImportSessionGroupingPanel
        inventoryId="inv-1"
        sessionId="sess-1"
        session={baseSession()}
        items={items}
        ungroupedCount={0}
        onRefresh={() => {}}
      />
    );
    const previewBtn = screen.getByRole('button', { name: 'Preview' });
    expect(previewBtn).toBeDisabled();
    const wrap = previewBtn.closest('span');
    expect(wrap).not.toBeNull();
    expect(within(wrap as HTMLElement).getByRole('button', { name: 'Preview' })).toBeInTheDocument();
    const labelled = previewBtn.closest('[aria-label]');
    expect(labelled).not.toBeNull();
    expect(labelled).toHaveAttribute('aria-label', 'Materialize this group before preview');
  });

  it('enables Preview when the group has a materialized item link', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-01T00:00:00Z',
            end_time: '2026-01-01T00:05:00Z',
            algorithm_version: 'time_gap_v1',
            assignment_status: 'assigned_existing',
            assigned_aisle_id: 'aisle-1',
            assigned_at: '2026-01-01T00:10:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    const items: CaptureSessionItemResponse[] = [
      {
        id: 'item-1',
        session_id: 'sess-1',
        staging_storage_key: 'k',
        import_status: 'imported',
        assignment_status: 'pending',
        updated_at: '2026-01-01T00:00:00Z',
        group_id: 'g-1',
        linked_source_asset_id: 'asset-1',
      },
    ];
    renderWithClient(
      <ImportSessionGroupingPanel
        inventoryId="inv-1"
        sessionId="sess-1"
        session={baseSession()}
        items={items}
        ungroupedCount={0}
        onRefresh={() => {}}
      />
    );
    const previewBtn = screen.getByRole('button', { name: 'Preview' });
    expect(previewBtn).not.toBeDisabled();
  });

  it('enables Preview when assigned but detail has no rows for that group (heuristic defers to API)', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-01T00:00:00Z',
            end_time: '2026-01-01T00:05:00Z',
            algorithm_version: 'time_gap_v1',
            assignment_status: 'assigned_existing',
            assigned_aisle_id: 'aisle-1',
            assigned_at: '2026-01-01T00:10:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    const items: CaptureSessionItemResponse[] = [
      {
        id: 'item-x',
        session_id: 'sess-1',
        staging_storage_key: 'k',
        import_status: 'imported',
        assignment_status: 'pending',
        updated_at: '2026-01-01T00:00:00Z',
        group_id: 'other-group',
        linked_source_asset_id: null,
      },
    ];
    renderWithClient(
      <ImportSessionGroupingPanel
        inventoryId="inv-1"
        sessionId="sess-1"
        session={baseSession()}
        items={items}
        ungroupedCount={0}
        onRefresh={() => {}}
      />
    );
    expect(screen.getByRole('button', { name: 'Preview' })).not.toBeDisabled();
  });

  it('preview dialog lists operational fields from API rows', async () => {
    const previewPayload = {
      capture_session_id: 'sess-1',
      group_id: 'g-1',
      aisle_id: 'aisle-1',
      source_asset_count: 1,
      source_asset_ids: ['asset-1'],
      preview_status: 'ready',
      preview_operator_state: 'ready',
      summary: { proposed_count: 1, conflict_count: 0, unassigned_count: 0, previewed_item_count: 1 },
      items: [
        {
          capture_session_item_id: 'item-1',
          source_asset_id: 'asset-1',
          assignment_status: 'proposed',
          assignment_reason: 'preview:ordered_position_slot:index=0;position_id=pos-1',
          adjusted_capture_time: '2026-01-01T12:00:00.000Z',
          preview_target_position_id: 'pos-1',
        },
      ],
    };
    mockUsePreviewMaterializedCaptureSessionGroup.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(previewPayload),
      isPending: false,
      error: null,
    });
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-01T00:00:00Z',
            end_time: '2026-01-01T00:05:00Z',
            algorithm_version: 'time_gap_v1',
            assignment_status: 'assigned_existing',
            assigned_aisle_id: 'aisle-1',
            assigned_at: '2026-01-01T00:10:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    const items: CaptureSessionItemResponse[] = [
      {
        id: 'item-1',
        session_id: 'sess-1',
        staging_storage_key: 'k',
        import_status: 'imported',
        assignment_status: 'pending',
        updated_at: '2026-01-01T00:00:00Z',
        group_id: 'g-1',
        linked_source_asset_id: 'asset-1',
      },
    ];
    renderWithClient(
      <ImportSessionGroupingPanel
        inventoryId="inv-1"
        sessionId="sess-1"
        session={baseSession()}
        items={items}
        ungroupedCount={0}
        onRefresh={() => {}}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    await waitFor(() => {
      expect(screen.getByText(/Reason: preview:ordered_position_slot/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Status: proposed/)).toBeInTheDocument();
    expect(screen.getByText(/Position: pos-1/)).toBeInTheDocument();
    expect(screen.getByText(/Item: item-1/)).toBeInTheDocument();
    expect(screen.getByText(/Asset: asset-1/)).toBeInTheDocument();
    expect(screen.getByText(/^Time:/)).toBeInTheDocument();
  });

  it('surfaces backend preview rejection in the grouping error alert', async () => {
    mockUsePreviewMaterializedCaptureSessionGroup.mockReturnValue({
      mutateAsync: vi.fn().mockRejectedValue(new Error('Materialize this capture session group before preview.')),
      isPending: false,
      error: null,
    });
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-01T00:00:00Z',
            end_time: '2026-01-01T00:05:00Z',
            algorithm_version: 'time_gap_v1',
            assignment_status: 'assigned_existing',
            assigned_aisle_id: 'aisle-1',
            assigned_at: '2026-01-01T00:10:00Z',
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    const items: CaptureSessionItemResponse[] = [
      {
        id: 'item-1',
        session_id: 'sess-1',
        staging_storage_key: 'k',
        import_status: 'imported',
        assignment_status: 'pending',
        updated_at: '2026-01-01T00:00:00Z',
        group_id: 'g-1',
        linked_source_asset_id: 'asset-1',
      },
    ];
    renderWithClient(
      <ImportSessionGroupingPanel
        inventoryId="inv-1"
        sessionId="sess-1"
        session={baseSession()}
        items={items}
        ungroupedCount={0}
        onRefresh={() => {}}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Materialize this capture session group before preview.');
    });
  });
});
