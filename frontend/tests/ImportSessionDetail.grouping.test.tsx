import '@testing-library/jest-dom/vitest';
import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ImportSessionDetail from '../src/features/ingestionSessions/components/ImportSessionDetail';
import type { CaptureSessionDetailResponse } from '../src/types/captureSession';

const mockUseCaptureSessionGroups = vi.fn();
const mockUseComputeCaptureSessionGroups = vi.fn();

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
    mockUseComputeCaptureSessionGroups.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
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
