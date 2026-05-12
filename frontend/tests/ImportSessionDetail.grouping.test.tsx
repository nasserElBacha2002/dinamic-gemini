import '@testing-library/jest-dom/vitest';
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ImportSessionDetail from '../src/features/ingestionSessions/components/ImportSessionDetail';
import type { CaptureSessionDetailResponse } from '../src/types/captureSession';

const mockUseCaptureSessionGroups = vi.fn();
const mockUseComputeCaptureSessionGroups = vi.fn();
const mockUseAisleOptions = vi.fn();
const mockUseAssignCaptureSessionGroupToExistingAisle = vi.fn();
const mockUseCreateAisleFromCaptureSessionGroup = vi.fn();
const mockUseInventoryDetail = vi.fn();
const mockUseClientSuppliers = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      if (key === 'ingestion_sessions.detail.grouping_row' && options) {
        return `Group ${options.index} — ${options.count} items — ${options.start} → ${options.end}`;
      }
      if (key === 'ingestion_sessions.detail.grouping_title') return 'Grouping';
      if (key === 'ingestion_sessions.detail.grouping_compute') return 'Compute groups';
      if (key === 'ingestion_sessions.detail.grouping_hint_close') return 'Close session hint';
      if (key === 'ingestion_sessions.detail.grouping_hint_blocked') return 'Blocked hint';
      if (key === 'ingestion_sessions.detail.grouping_loading') return 'Loading groups';
      if (key === 'ingestion_sessions.detail.grouping_empty') return 'No groups yet';
      if (key === 'ingestion_sessions.detail.grouping_ungrouped') return `Ungrouped: ${options?.count ?? 0}`;
      if (key === 'ingestion_sessions.detail.grouping_assignment_unassigned') return 'Unassigned';
      if (key === 'ingestion_sessions.detail.grouping_assignment_existing') return 'Assigned existing';
      if (key === 'ingestion_sessions.detail.grouping_assignment_new') return 'New aisle';
      if (key === 'ingestion_sessions.detail.grouping_assign_existing') return 'Assign to aisle';
      if (key === 'ingestion_sessions.detail.grouping_create_aisle') return 'Create aisle';
      if (key.startsWith('ingestion_sessions.detail.')) return key;
      if (key.startsWith('ingestion_sessions.actions.')) return key;
      return key;
    },
  }),
}));

vi.mock('../src/features/ingestionSessions/components/ImportSessionUpload', () => ({
  default: () => null,
}));

vi.mock('../src/hooks/useInventories', () => ({
  useInventoryDetail: (...args: unknown[]) => mockUseInventoryDetail(...args),
}));

vi.mock('../src/hooks/useClients', () => ({
  useClientSuppliers: (...args: unknown[]) => mockUseClientSuppliers(...args),
}));

vi.mock('../src/features/ingestionSessions/hooks/useCaptureSessions', () => ({
  useCaptureSessionGroups: (...args: unknown[]) => mockUseCaptureSessionGroups(...args),
  useComputeCaptureSessionGroups: () => mockUseComputeCaptureSessionGroups(),
  useAisleOptions: (...args: unknown[]) => mockUseAisleOptions(...args),
  useAssignCaptureSessionGroupToExistingAisle: () => mockUseAssignCaptureSessionGroupToExistingAisle(),
  useCreateAisleFromCaptureSessionGroup: () => mockUseCreateAisleFromCaptureSessionGroup(),
  useMaterializeCaptureSessionGroup: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    error: null,
  }),
  usePreviewMaterializedCaptureSessionGroup: () => ({
    mutateAsync: vi.fn().mockResolvedValue({
      capture_session_id: 'sess-1',
      group_id: 'g1',
      aisle_id: 'aisle-1',
      source_asset_count: 0,
      source_asset_ids: [],
      preview_status: 'empty',
      items: [],
      summary: { proposed_count: 0, conflict_count: 0, unassigned_count: 0, previewed_item_count: 0 },
    }),
    isPending: false,
    error: null,
  }),
}));

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function buildDetail(overrides: Partial<CaptureSessionDetailResponse['session']>): CaptureSessionDetailResponse {
  return {
    session: {
      id: 'sess-1',
      inventory_id: 'inv-1',
      aisle_id: null,
      status: 'draft',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      opened_at: null,
      closed_at: null,
      clock_offset_seconds: 0,
      ...overrides,
    },
    items: [],
  };
}

describe('ImportSessionDetail — G3 grouping', () => {
  beforeEach(() => {
    mockUseCaptureSessionGroups.mockReset();
    mockUseComputeCaptureSessionGroups.mockReset();
    mockUseAisleOptions.mockReset();
    mockUseAssignCaptureSessionGroupToExistingAisle.mockReset();
    mockUseCreateAisleFromCaptureSessionGroup.mockReset();
    mockUseInventoryDetail.mockReset();
    mockUseClientSuppliers.mockReset();
    mockUseComputeCaptureSessionGroups.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    });
    mockUseAisleOptions.mockReturnValue({
      data: { items: [{ id: 'a1', code: 'A-01' }], page: 1, page_size: 200, total_items: 1, total_pages: 1 },
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
    mockUseInventoryDetail.mockReturnValue({
      data: {
        id: 'inv-1',
        client_id: 'client-1',
        name: 'Inv',
        status: 'draft',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      isLoading: false,
      isError: false,
    });
    mockUseClientSuppliers.mockReturnValue({
      data: {
        items: [{ id: 'sup-1', name: 'S', status: 'active', client_id: 'client-1', created_at: '', updated_at: '' }],
        page: 1,
        page_size: 200,
        total_items: 1,
        total_pages: 1,
      },
      isLoading: false,
      isError: false,
    });
  });

  it('shows close-session hint when temporal grouping is not enabled (open session)', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    });
    const detail = buildDetail({ closed_at: null, status: 'draft' });
    renderWithClient(
      <ImportSessionDetail
        detail={detail}
        canUpload
        canClose={false}
        canCancel
        closing={false}
        cancelling={false}
        onCloseSession={() => {}}
        onCancelSession={() => {}}
        onRefresh={() => {}}
      />
    );
    expect(screen.getByText('Close session hint')).toBeInTheDocument();
    expect(screen.queryByText('Compute groups')).not.toBeInTheDocument();
  });

  it('renders a group row when session is closed and groups query returns summaries', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 2,
            start_time: '2026-01-02T12:01:00.000Z',
            end_time: '2026-01-02T12:05:00.000Z',
            algorithm_version: 'time_gap_v1',
            assignment_status: 'unassigned',
            assigned_aisle_id: null,
            assigned_at: null,
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    const detail = buildDetail({
      closed_at: '2026-01-02T10:00:00.000Z',
      status: 'ready_for_review',
    });
    detail.items = [
      {
        id: 'i1',
        session_id: 'sess-1',
        staging_storage_key: 'k1',
        import_status: 'imported',
        assignment_status: 'pending',
        effective_capture_time: '2026-01-02T12:01:00.000Z',
        updated_at: '2026-01-02T11:00:00.000Z',
        group_id: 'g-1',
      },
    ];
    renderWithClient(
      <ImportSessionDetail
        detail={detail}
        canUpload={false}
        canClose={false}
        canCancel
        closing={false}
        cancelling={false}
        onCloseSession={() => {}}
        onCancelSession={() => {}}
        onRefresh={() => {}}
      />
    );
    expect(screen.getByText('Compute groups')).toBeInTheDocument();
    expect(screen.getByText(/Group 1 — 2 items —/)).toBeInTheDocument();
  });
});
