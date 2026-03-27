/**
 * Canonical review drawer — evidence, actions, prev/next (detail loaded via useResultDetail).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import QuickReviewDrawer from '../src/features/reviewQueue/components/QuickReviewDrawer';
import type { QuickReviewContext } from '../src/features/reviewQueue/quickReviewContext';
import { AppSnackbarProvider } from '../src/components/ui';
import { mapPositionDetailToResultDetail } from '../src/features/results/mappers/positionToResult';

const basePosition = {
  id: 'pos-1',
  aisle_id: 'aisle-1',
  status: 'detected',
  sku: 'SKU001',
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
    evidences: [],
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

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSubmitReviewAction: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    }),
  };
});

const baseContext: QuickReviewContext = {
  inventoryId: 'inv-1',
  inventoryName: 'Test Inventory',
  aisleCode: 'A-01',
  aisleId: 'aisle-1',
  positionId: 'pos-1',
  resultIds: ['pos-1'],
  returnTo: 'aisle_results',
};

function renderDrawer(context: QuickReviewContext) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AppSnackbarProvider>
        <QuickReviewDrawer open context={context} onClose={() => {}} />
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

function mockResultDetail(overrides: Partial<ReturnType<typeof mapPositionDetailToResultDetail>> = {}) {
  const data = createDetailData(basePosition);
  const result = mapPositionDetailToResultDetail(data);
  return { ...result, ...overrides };
}

describe('QuickReviewDrawer', () => {
  it('shows Result heading when result loads', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer(baseContext);
    const heading = await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(heading).toBeInTheDocument();
  });

  it('shows Evidence and source filename when present', async () => {
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

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(screen.getByText(/IMG_1024.JPG/)).toBeInTheDocument();
  });

  it('shows Open fullscreen when sourceImageId is present', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail({ sourceImageId: 'asset-uuid-123' }),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByRole('button', { name: /Open fullscreen/i })).toBeInTheDocument();
  });

  it('shows no-evidence state when no source image', async () => {
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

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(screen.getByText(/No image evidence available/)).toBeInTheDocument();
  });

  it('opens shared confirm dialog when Mark result invalid is clicked', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /Mark result invalid/i }));
    expect(await screen.findByRole('heading', { name: /Mark result invalid\?/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  });

  it('shows Review actions and Confirm result', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText('Review actions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm result/i })).toBeInTheDocument();
  });

  it('shows prev/next when resultIds has multiple and position is in list', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer({
      ...baseContext,
      positionId: 'pos-1',
      resultIds: ['pos-0', 'pos-1', 'pos-2'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/Result 2 of 3/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Previous result/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Next result/i })).toBeInTheDocument();
  });

  it('hides prev/next when only one id in list', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer({ ...baseContext, resultIds: ['pos-1'] });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.queryByText(/Result \d+ of \d+/)).not.toBeInTheDocument();
  });

  it('hides prev/next when current id not in resultIds', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer({
      ...baseContext,
      positionId: 'pos-1',
      resultIds: ['other-1', 'other-2'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.queryByText(/Result \d+ of \d+/)).not.toBeInTheDocument();
  });

  it('first of three disables Previous', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer({
      ...baseContext,
      positionId: 'pos-1',
      resultIds: ['pos-1', 'pos-2', 'pos-3'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/Result 1 of 3/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Previous result/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Next result/i })).not.toBeDisabled();
  });

  it('last of three disables Next', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue({
      result: mockResultDetail(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof useResultDetail>);

    renderDrawer({
      ...baseContext,
      positionId: 'pos-3',
      resultIds: ['pos-1', 'pos-2', 'pos-3'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/Result 3 of 3/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Previous result/i })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /Next result/i })).toBeDisabled();
  });
});
