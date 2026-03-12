/**
 * PositionDetailPage (Epic 4) — Result-centric detail; Evidence and source file display.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PositionDetailPage from '../src/pages/PositionDetailPage';
import { mapPositionDetailToResultDetail } from '../src/features/results/mappers/positionToResult';

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

vi.mock('../src/features/results', () => ({
  useResultDetail: vi.fn(),
}));

vi.mock('../src/hooks', () => ({
  useSubmitReviewAction: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
}));

function renderPage(initialEntry = '/inventories/inv-1/aisles/aisle-1/positions/pos-1') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
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
});
