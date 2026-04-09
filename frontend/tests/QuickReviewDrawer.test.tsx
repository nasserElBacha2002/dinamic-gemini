/**
 * Canonical review drawer — evidence, actions, prev/next (detail loaded via useResultDetail).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import QuickReviewDrawer from '../src/features/reviewQueue/components/QuickReviewDrawer';
import type { QuickReviewContext } from '../src/features/reviewQueue/quickReviewContext';
import { mapPositionDetailToResultDetail } from '../src/features/results/mappers/positionToResult';
import { ApiError } from '../src/api/types';

const reviewMutateAsync = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const showSnackbarMock = vi.hoisted(() => vi.fn());

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
      mutateAsync: reviewMutateAsync,
      isPending: false,
      isError: false,
      error: null,
    }),
  };
});

vi.mock('../src/components/ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/components/ui')>();
  return {
    ...actual,
    useAppSnackbar: () => ({
      showSnackbar: showSnackbarMock,
      closeSnackbar: vi.fn(),
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
      <QuickReviewDrawer open context={context} onClose={() => {}} />
    </QueryClientProvider>
  );
}

function mockResultDetail(overrides: Partial<ReturnType<typeof mapPositionDetailToResultDetail>> = {}) {
  const data = createDetailData(basePosition);
  const result = mapPositionDetailToResultDetail(data);
  return { ...result, ...overrides };
}

describe('QuickReviewDrawer', () => {
  beforeEach(() => {
    reviewMutateAsync.mockClear();
    showSnackbarMock.mockClear();
  });

  it('Wrong image triggers mark_image_mismatch mutation', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: /Wrong image/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'mark_image_mismatch' });
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('Flagged wrong image (traceability)', 'success');
  });

  it('confirm result triggers exactly one mutation request', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: /Confirm result/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'confirm' });
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('Result confirmed', 'success');
  });

  it('rapid double-click confirm still triggers only one mutation', async () => {
    let resolveMutate: (() => void) | undefined;
    const mutatePromise = new Promise<void>((resolve) => {
      resolveMutate = resolve;
    });
    reviewMutateAsync.mockImplementationOnce(() => mutatePromise);

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
    const confirmBtn = screen.getByRole('button', { name: /Confirm result/i });
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    resolveMutate?.();
  });

  it('update quantity triggers exactly one mutation request', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: /Correct quantity/i }));
    fireEvent.change(screen.getByPlaceholderText('0'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({
      action_type: 'update_quantity',
      corrected_quantity: 5,
    });
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('Quantity updated', 'success');
  });

  it('update SKU triggers exactly one mutation request', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: /Correct SKU/i }));
    fireEvent.change(screen.getByPlaceholderText(/Update SKU/i), { target: { value: 'NEW-SKU' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({
      action_type: 'update_sku',
      sku: 'NEW-SKU',
    });
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('SKU updated', 'success');
  });

  it('mark invalid confirm shows inline error in dialog when mutation fails', async () => {
    reviewMutateAsync.mockRejectedValueOnce(new ApiError('Not allowed', 403));
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
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mark invalid' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/Not allowed|could not complete/i);
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'delete_position' });
  });

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

  it('shows Preview when sourceImageId is present', async () => {
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
    expect(screen.getByRole('button', { name: /^Preview$/i })).toBeInTheDocument();
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

  it('shows review controls: confirm and wrong-image action', async () => {
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
    expect(screen.getByRole('button', { name: /Confirm result/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Wrong image/i })).toBeInTheDocument();
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
      result: mockResultDetail({ id: 'pos-3' }),
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
