import '@testing-library/jest-dom/vitest';
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ImportSessionDetail from '../src/features/ingestionSessions/components/ImportSessionDetail';
import type { CaptureSessionDetailResponse } from '../src/types/captureSession';

const mockUseCaptureSessionGroups = vi.fn();
const mockUseComputeCaptureSessionGroups = vi.fn();
const mockUseAisleOptions = vi.fn();
const mockUseAssignCaptureSessionGroupToExistingAisle = vi.fn();
const mockUseCreateAisleFromCaptureSessionGroup = vi.fn();

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
      if (key === 'ingestion_sessions.detail.grouping_assign_dialog_title') return 'Assign dialog title';
      if (key === 'ingestion_sessions.detail.grouping_create_dialog_title') return 'Create dialog title';
      if (key === 'ingestion_sessions.detail.grouping_create_dialog_code_label') return 'Aisle code';
      if (key.startsWith('ingestion_sessions.detail.')) return key;
      if (key.startsWith('ingestion_sessions.actions.')) return key;
      return key;
    },
  }),
}));

vi.mock('../src/features/ingestionSessions/components/ImportSessionUpload', () => ({
  default: () => null,
}));

vi.mock('../src/features/ingestionSessions/hooks/useCaptureSessions', () => ({
  useCaptureSessionGroups: (...args: unknown[]) => mockUseCaptureSessionGroups(...args),
  useComputeCaptureSessionGroups: () => mockUseComputeCaptureSessionGroups(),
  useAisleOptions: (...args: unknown[]) => mockUseAisleOptions(...args),
  useAssignCaptureSessionGroupToExistingAisle: () => mockUseAssignCaptureSessionGroupToExistingAisle(),
  useCreateAisleFromCaptureSessionGroup: () => mockUseCreateAisleFromCaptureSessionGroup(),
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

describe('ImportSessionDetail — G4 group → aisle', () => {
  beforeEach(() => {
    mockUseCaptureSessionGroups.mockReset();
    mockUseComputeCaptureSessionGroups.mockReset();
    mockUseAisleOptions.mockReset();
    mockUseAssignCaptureSessionGroupToExistingAisle.mockReset();
    mockUseCreateAisleFromCaptureSessionGroup.mockReset();
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
      mutateAsync: vi.fn().mockResolvedValue({ groups: [] }),
      isPending: false,
      error: null,
    });
    mockUseCreateAisleFromCaptureSessionGroup.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ groups: [] }),
      isPending: false,
      error: null,
    });
  });

  it('opens assign dialog when clicking Assign to aisle on an unassigned group', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-02T12:01:00.000Z',
            end_time: '2026-01-02T12:02:00.000Z',
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
    fireEvent.click(screen.getByText('Assign to aisle'));
    expect(screen.getByText('Assign dialog title')).toBeInTheDocument();
  });

  it('opens create-aisle dialog when clicking Create aisle', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-02T12:01:00.000Z',
            end_time: '2026-01-02T12:02:00.000Z',
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
    fireEvent.click(screen.getByText('Create aisle'));
    expect(screen.getByText('Create dialog title')).toBeInTheDocument();
    expect(screen.getByLabelText('Aisle code')).toBeInTheDocument();
  });

  it('does not show assign actions when group is already assigned to an existing aisle', () => {
    mockUseCaptureSessionGroups.mockReturnValue({
      data: {
        groups: [
          {
            group_id: 'g-1',
            group_index: 1,
            item_count: 1,
            start_time: '2026-01-02T12:01:00.000Z',
            end_time: '2026-01-02T12:02:00.000Z',
            algorithm_version: 'time_gap_v1',
            assignment_status: 'assigned_existing',
            assigned_aisle_id: 'aisle-1',
            assigned_at: '2026-01-02T12:30:00.000Z',
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
    expect(screen.getByText('Assigned existing')).toBeInTheDocument();
    expect(screen.queryByText('Assign to aisle')).not.toBeInTheDocument();
  });
});
