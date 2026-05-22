import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import QuickReviewDrawer from '../src/features/reviewQueue/components/QuickReviewDrawer';
import type { QuickReviewContext } from '../src/features/reviewQueue/quickReviewContext';

const reviewMutateAsync = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const submitReviewArgsMock = vi.hoisted(() => vi.fn());

vi.mock('../src/features/results', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/features/results')>();
  return {
    ...actual,
    useResultDetail: vi.fn(() => ({
      result: {
        id: 'pos-representative',
        sku: 'SKU-CANON',
        detectedQty: 4,
        correctedQty: null,
        resolvedQty: 4,
        systemQty: 4,
        qtySource: 'consolidated',
        qtyResolved: true,
        qtyInferenceReason: null,
        confidence: 0.9,
        reviewStatus: 'CONFIRMED',
        traceabilityStatus: 'UNVALIDATED',
        needsReview: false,
        updatedAt: '2024-01-01T00:00:00Z',
        sourceImageId: null,
        sourceFileName: null,
        evidence: [],
        reviewHistory: [],
        technicalMetadata: {},
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    })),
  };
});

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSubmitReviewAction: (inventoryId: string, aisleId: string, positionId: string) => {
      submitReviewArgsMock(inventoryId, aisleId, positionId);
      return {
        mutateAsync: reviewMutateAsync,
        isPending: false,
        isError: false,
        error: null,
      };
    },
  };
});

vi.mock('../src/components/ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/components/ui')>();
  return {
    ...actual,
    useAppSnackbar: () => ({
      showSnackbar: vi.fn(),
      closeSnackbar: vi.fn(),
    }),
  };
});

const context: QuickReviewContext = {
  inventoryId: 'inv-1',
  inventoryName: 'Inventory',
  aisleCode: 'A-01',
  aisleId: 'aisle-1',
  positionId: 'pos-member',
  resultIds: ['pos-representative'],
  returnTo: 'aisle_results',
};

function renderDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuickReviewDrawer open context={context} onClose={() => {}} />
    </QueryClientProvider>
  );
}

describe('QuickReviewDrawer representative anchor sync', () => {
  beforeEach(() => {
    reviewMutateAsync.mockClear();
    submitReviewArgsMock.mockClear();
  });

  it('re-targets review actions to the canonical representative id returned by detail', async () => {
    renderDrawer();

    await screen.findByRole('heading', { level: 1, name: 'SKU-CANON' });
    await waitFor(() => {
      expect(submitReviewArgsMock).toHaveBeenLastCalledWith('inv-1', 'aisle-1', 'pos-representative');
    });
    fireEvent.click(screen.getByRole('button', { name: /confirmar resultado|confirm result/i }));

    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'confirm' });
    expect(submitReviewArgsMock).toHaveBeenLastCalledWith('inv-1', 'aisle-1', 'pos-representative');
    expect(submitReviewArgsMock.mock.calls).toEqual([['inv-1', 'aisle-1', 'pos-representative']]);
  });
});
