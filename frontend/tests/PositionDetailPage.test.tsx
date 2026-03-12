/**
 * PositionDetailPage (Epic 4) — Result-centric detail; Evidence and source file display.
 * Epic 5 — Previous/next navigation when navigation state is present.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PositionDetailPage from '../src/pages/PositionDetailPage';
import { mapPositionDetailToResultDetail } from '../src/features/results/mappers/positionToResult';
import type { ResultDetailNavigationState } from '../src/features/results';

const basePosition = {
  id: 'pos-1',
  aisle_id: 'aisle-1',
  status: 'detected',
  confidence: 0.9,
  needs_review: false,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const mockProducts = [
  {
    id: 'pr-1',
    position_id: 'pos-1',
    sku: 'SKU001',
    detected_quantity: 2,
    confidence: 0.9,
    created_at: '2024-01-01T00:00:00Z',
  },
];
const mockEvidences: Array<{
  id: string;
  entity_type: string;
  entity_id: string;
  type: string;
  storage_path: string;
  is_primary: boolean;
}> = [];

function createDetailData(
  position: typeof basePosition & {
    source_image_id?: string | null;
    source_image_original_filename?: string | null;
    traceability_status?: string | null;
  }
) {
  return {
    position: { ...basePosition, ...position },
    products: mockProducts,
    evidences: mockEvidences,
    review_actions: [],
  };
}

vi.mock('../src/features/results', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/features/results')>();
  return {
    ...actual,
    useResultDetail: vi.fn(),
  };
});

vi.mock('../src/hooks', () => ({
  useSubmitReviewAction: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
}));

function renderPage(
  initialEntry: string | { pathname: string; state?: ResultDetailNavigationState } = '/inventories/inv-1/aisles/aisle-1/positions/pos-1'
) {
  const entry = typeof initialEntry === 'string' ? initialEntry : initialEntry;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/inventories/:inventoryId/aisles/:aisleId/positions/:positionId"
            element={<PositionDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mockResultDetail(
  overrides: Partial<ReturnType<typeof mapPositionDetailToResultDetail>> = {}
) {
  const data = createDetailData(basePosition);
  const result = mapPositionDetailToResultDetail(data);
  return { ...result, ...overrides };
}

describe('PositionDetailPage (Epic 4 Result-centric)', () => {
  it('shows Result header when result loads', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderPage();
    await screen.findByText('Result');
    expect(screen.getByText('Result')).toBeInTheDocument();
  });

  it('shows Evidence section with Source file when source_image_original_filename is present', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail({
        sourceImageId: 'img_002',
        sourceFileName: 'IMG_1024.JPG',
      }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderPage();
    await screen.findByText('Result');
    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(screen.getByText(/Source file:/)).toBeInTheDocument();
    expect(screen.getByText(/IMG_1024.JPG/)).toBeInTheDocument();
  });

  it('shows View full image button when sourceImageId is present', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail({ sourceImageId: 'asset-uuid-123' }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderPage();
    await screen.findByText('Result');
    expect(screen.getByRole('button', { name: /View full image/i })).toBeInTheDocument();
  });

  it('shows no-evidence state when sourceImageId and evidence are empty', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail({
        sourceImageId: null,
        sourceFileName: null,
        evidence: [],
      }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderPage();
    await screen.findByText('Result');
    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(screen.getByText(/No evidence available/)).toBeInTheDocument();
  });

  it('shows Review actions and Confirm result button', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderPage();
    await screen.findByText('Result');
    expect(screen.getByText('Review actions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm result/i })).toBeInTheDocument();
  });

  it('Epic 5: shows Result X of Y and Previous/Next when navigation state is present', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    const navState: ResultDetailNavigationState = {
      resultIds: ['pos-0', 'pos-1', 'pos-2'],
      filter: 'all',
    };
    renderPage({
      pathname: '/inventories/inv-1/aisles/aisle-1/positions/pos-1',
      state: navState,
    });

    await screen.findByText('Result');
    expect(screen.getByText(/Result 2 of 3/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Previous result/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Next result/i })).toBeInTheDocument();
  });

  it('Epic 5: does not show prev/next when no navigation state', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderPage('/inventories/inv-1/aisles/aisle-1/positions/pos-1');

    await screen.findByText('Result');
    expect(screen.queryByText(/Result \d+ of \d+/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Previous result/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Next result/i })).not.toBeInTheDocument();
  });

  it('Epic 5: does not show prev/next when navigation state is malformed', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderPage({
      pathname: '/inventories/inv-1/aisles/aisle-1/positions/pos-1',
      state: { resultIds: 'not-an-array' },
    });

    await screen.findByText('Result');
    expect(screen.queryByText(/Result \d+ of \d+/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Previous result/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Next result/i })).not.toBeInTheDocument();
  });

  it('Epic 5: does not show prev/next when current result ID is not in resultIds', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    const navState: ResultDetailNavigationState = {
      resultIds: ['other-1', 'other-2'],
      filter: 'all',
    };
    renderPage({
      pathname: '/inventories/inv-1/aisles/aisle-1/positions/pos-1',
      state: navState,
    });

    await screen.findByText('Result');
    expect(screen.queryByText(/Result \d+ of \d+/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Previous result/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Next result/i })).not.toBeInTheDocument();
  });

  it('Epic 5: first result disables Previous button', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    const navState: ResultDetailNavigationState = {
      resultIds: ['pos-1', 'pos-2', 'pos-3'],
      filter: 'all',
    };
    renderPage({
      pathname: '/inventories/inv-1/aisles/aisle-1/positions/pos-1',
      state: navState,
    });

    await screen.findByText('Result');
    expect(screen.getByText(/Result 1 of 3/)).toBeInTheDocument();
    const prevBtn = screen.getByRole('button', { name: /Previous result/i });
    expect(prevBtn).toBeDisabled();
    expect(screen.getByRole('button', { name: /Next result/i })).not.toBeDisabled();
  });

  it('Epic 5: last result disables Next button', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    const navState: ResultDetailNavigationState = {
      resultIds: ['pos-1', 'pos-2', 'pos-3'],
      filter: 'all',
    };
    renderPage({
      pathname: '/inventories/inv-1/aisles/aisle-1/positions/pos-3',
      state: navState,
    });

    await screen.findByText('Result');
    expect(screen.getByText(/Result 3 of 3/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Previous result/i })).not.toBeDisabled();
    const nextBtn = screen.getByRole('button', { name: /Next result/i });
    expect(nextBtn).toBeDisabled();
  });
});
