import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import IngestionSessionDetailPage from '../src/features/ingestionSessions/pages/IngestionSessionDetailPage';
import { hasRequiredDetailParams } from '../src/features/ingestionSessions/utils/ingestionSessionDetailParams';
import { buildSessionsListParams } from '../src/features/ingestionSessions/utils/ingestionSessionsListParams';

const mockUseCaptureSessionDetail = vi.fn();
const mockUseCloseCaptureSession = vi.fn();
const mockUseCancelCaptureSession = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../src/features/ingestionSessions/hooks/useCaptureSessions', () => ({
  useCaptureSessionDetail: (...args: unknown[]) => mockUseCaptureSessionDetail(...args),
  useCloseCaptureSession: (...args: unknown[]) => mockUseCloseCaptureSession(...args),
  useCancelCaptureSession: (...args: unknown[]) => mockUseCancelCaptureSession(...args),
}));

function renderDetail(url: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/ingestion-sessions/:sessionId" element={<IngestionSessionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('R2 corrections — ingestion sessions', () => {
  beforeEach(() => {
    mockUseCloseCaptureSession.mockReset();
    mockUseCancelCaptureSession.mockReset();
    mockUseCaptureSessionDetail.mockReset();
  });

  it('builds list params without aisle filter when aisle is not explicitly selected', () => {
    expect(buildSessionsListParams('inv-1', '')).toEqual({
      inventoryId: 'inv-1',
      aisleId: undefined,
      page: 1,
      pageSize: 100,
    });
    expect(buildSessionsListParams('inv-1', 'aisle-9')).toEqual({
      inventoryId: 'inv-1',
      aisleId: 'aisle-9',
      page: 1,
      pageSize: 100,
    });
  });

  it('requires only inventoryId + sessionId for detail readiness', () => {
    expect(hasRequiredDetailParams('inv-1', 'sess-1')).toBe(true);
    expect(hasRequiredDetailParams('inv-1', undefined)).toBe(false);
    expect(hasRequiredDetailParams('', 'sess-1')).toBe(false);
  });

  it('does not require aisleId in URL and closes session using aisle from loaded detail', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    const cancelMutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseCloseCaptureSession.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });
    mockUseCancelCaptureSession.mockReturnValue({
      mutateAsync: cancelMutateAsync,
      isPending: false,
      error: null,
    });
    mockUseCaptureSessionDetail.mockReturnValue({
      data: {
        session: {
          id: 'sess-1',
          inventory_id: 'inv-1',
          aisle_id: 'aisle-derived',
          status: 'importing',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          opened_at: null,
          closed_at: null,
          clock_offset_seconds: 0,
        },
        items: [
          {
            id: 'item-1',
            session_id: 'sess-1',
            staging_storage_key: 'capture/staging/example.jpg',
            import_status: 'imported',
            assignment_status: 'pending',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
      },
      isPending: false,
      error: null,
      refetch: vi.fn(),
    });

    renderDetail('/ingestion-sessions/sess-1?inventoryId=inv-1');

    // i18n is mocked as key passthrough, proving UI strings are sourced from translation keys.
    expect(screen.getByText('ingestion_sessions.detail.page_title')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'ingestion_sessions.actions.close_session' }));

    expect(mutateAsync).toHaveBeenCalledWith({
      inventoryId: 'inv-1',
      sessionId: 'sess-1',
      aisleId: 'aisle-derived',
    });
    fireEvent.click(screen.getByRole('button', { name: 'ingestion_sessions.actions.cancel_session' }));
    expect(cancelMutateAsync).toHaveBeenCalledWith({
      inventoryId: 'inv-1',
      sessionId: 'sess-1',
    });
  });

  it('allows close for inventory-level session without requiring aisleId', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockUseCloseCaptureSession.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });
    mockUseCancelCaptureSession.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(undefined),
      isPending: false,
      error: null,
    });
    mockUseCaptureSessionDetail.mockReturnValue({
      data: {
        session: {
          id: 'sess-inv',
          inventory_id: 'inv-1',
          aisle_id: null,
          status: 'importing',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          opened_at: null,
          closed_at: null,
          clock_offset_seconds: 0,
        },
        items: [
          {
            id: 'item-1',
            session_id: 'sess-inv',
            staging_storage_key: 'capture/staging/example.jpg',
            import_status: 'imported',
            assignment_status: 'pending',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
      },
      isPending: false,
      error: null,
      refetch: vi.fn(),
    });

    renderDetail('/ingestion-sessions/sess-inv?inventoryId=inv-1');
    fireEvent.click(screen.getByRole('button', { name: 'ingestion_sessions.actions.close_session' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      inventoryId: 'inv-1',
      sessionId: 'sess-inv',
      aisleId: undefined,
    });
  });
});
