/**
 * PositionDetailPage — source_image_id and source_image_original_filename (Epic 5) display; legacy-safe fallback.
 * Source image ID = internal traceability id; Source file = original filename when available.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PositionDetailPage from '../src/pages/PositionDetailPage';
import { usePositionDetail } from '../src/hooks';

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
const mockEvidences: Array<{ id: string; entity_type: string; entity_id: string; type: string; storage_path: string; is_primary: boolean }> = [];

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

vi.mock('../src/hooks', () => ({
  usePositionDetail: vi.fn(),
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

describe('PositionDetailPage source_image_id and Epic 5 source file', () => {
  it('shows Source image ID label and value when source_image_id is present', async () => {
    vi.mocked(usePositionDetail).mockReturnValue({
      data: createDetailData({ ...basePosition, source_image_id: 'img_abc123' }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof usePositionDetail>);

    renderPage();
    await screen.findByText(/Position detail/);
    expect(screen.getByText(/Source image ID:/)).toBeInTheDocument();
    expect(screen.getByText(/img_abc123/)).toBeInTheDocument();
  });

  it('shows Source image ID label with em dash when source_image_id is absent', async () => {
    vi.mocked(usePositionDetail).mockReturnValue({
      data: createDetailData({ ...basePosition, source_image_id: undefined }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof usePositionDetail>);

    renderPage();
    await screen.findByText(/Position detail/);
    expect(screen.getByText(/Source image ID:/)).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/Source image ID:\s*—/);
  });

  it('shows em dash when source_image_id is null or empty string', async () => {
    vi.mocked(usePositionDetail).mockReturnValue({
      data: createDetailData({ ...basePosition, source_image_id: null }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof usePositionDetail>);

    renderPage();
    await screen.findByText(/Position detail/);
    expect(screen.getByText(/Source image ID:/)).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/Source image ID:\s*—/);
  });

  it('Epic 5: shows Source file when source_image_original_filename is present', async () => {
    vi.mocked(usePositionDetail).mockReturnValue({
      data: createDetailData({
        ...basePosition,
        source_image_id: 'img_002',
        source_image_original_filename: 'IMG_1024.JPG',
      }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof usePositionDetail>);

    renderPage();
    await screen.findByText(/Position detail/);
    expect(screen.getByText(/Source file:/)).toBeInTheDocument();
    expect(screen.getByText(/IMG_1024.JPG/)).toBeInTheDocument();
  });

  it('Epic 5: Source file shows em dash when source_image_original_filename absent (legacy)', async () => {
    vi.mocked(usePositionDetail).mockReturnValue({
      data: createDetailData({ ...basePosition, source_image_id: 'img_001', source_image_original_filename: undefined }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof usePositionDetail>);

    renderPage();
    await screen.findByText(/Position detail/);
    expect(screen.getByText(/Source file:/)).toBeInTheDocument();
    expect(document.body.textContent).toMatch(/Source file:\s*—/);
  });

  it('shows View reference image button when source_image_id is present', async () => {
    vi.mocked(usePositionDetail).mockReturnValue({
      data: createDetailData({ ...basePosition, source_image_id: 'asset-uuid-123' }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof usePositionDetail>);

    renderPage('/inventories/inv-1/aisles/aisle-1/positions/pos-1');
    await screen.findByText(/Position detail/);
    expect(screen.getByRole('button', { name: /View reference image/i })).toBeInTheDocument();
  });

  it('does not show View reference image button when source_image_id is absent', async () => {
    vi.mocked(usePositionDetail).mockReturnValue({
      data: createDetailData({ ...basePosition, source_image_id: undefined }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof usePositionDetail>);

    renderPage();
    await screen.findByText(/Position detail/);
    expect(screen.queryByRole('button', { name: /View reference image/i })).not.toBeInTheDocument();
  });
});
