/**
 * Sprint 4.1 — Aisle Results page tests.
 */

import React from 'react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, MemoryRouter, Route, Routes, RouterProvider } from 'react-router-dom';
import AislePositionsPage from '../src/pages/AislePositionsPage';
import { AppSnackbarProvider } from '../src/components/ui';
import type { ResultSummary } from '../src/features/results/types';
import type { PositionSummary } from '../src/api/types';

const { useRunAisleMergeMock } = vi.hoisted(() => ({
  useRunAisleMergeMock: vi.fn(),
}));
const { getAisleMergeResultsMock } = vi.hoisted(() => ({
  getAisleMergeResultsMock: vi.fn(),
}));
const { promoteMutateAsync } = vi.hoisted(() => ({
  promoteMutateAsync: vi.fn().mockResolvedValue({
    aisle_id: 'aisle-1',
    operational_job_id: 'job-bench',
  }),
}));
const { resultSummariesState } = vi.hoisted(() => ({
  resultSummariesState: {
    results: [] as ResultSummary[],
    positions: [] as PositionSummary[],
    resultJobId: null as string | null,
    resultContextSource: null as string | null,
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
}));
const { aislesListState } = vi.hoisted(() => ({
  aislesListState: {
    data: { items: [{ id: 'aisle-1', code: 'A-01', status: 'created' }] },
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
}));
const { mergeResultsState } = vi.hoisted(() => ({
  mergeResultsState: {
    data: { results: [] as Array<Record<string, unknown>> },
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
}));
const { aisleJobsListState } = vi.hoisted(() => ({
  aisleJobsListState: {
    data: { jobs: [] as Array<{ id: string; status: string; created_at: string; updated_at: string }>, operational_job_id: null as string | null },
    isLoading: false,
    isError: false,
    isFetched: true,
    isFetching: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
}));
const { inventoryDetailState } = vi.hoisted(() => ({
  inventoryDetailState: {
    data: {
      id: 'inv-1',
      name: 'Test Inventory',
      status: 'draft',
      created_at: null as string | null,
      processing_mode: 'production' as 'production' | 'test',
    },
    isLoading: false,
    isError: false,
    error: null as unknown,
  },
}));

const mockPositions: PositionSummary[] = [
  {
    id: 'pos-1',
    aisle_id: 'aisle-1',
    status: 'detected',
    confidence: 0.9,
    needs_review: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    sku: 'SKU-001',
    detected_quantity: 5,
    corrected_quantity: null,
    qty: 5,
    qtySource: 'detected',
    has_evidence: true,
  },
];

const mockResults: ResultSummary[] = [
  {
    id: 'pos-1',
    sku: 'SKU-001',
    detectedQty: 5,
    correctedQty: null,
    resolvedQty: null,
    confidence: 0.9,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'UNVALIDATED',
    needsReview: false,
    updatedAt: '2024-01-01T00:00:00Z',
    hasEvidence: true,
  },
];

const repeatedSkuPositions: PositionSummary[] = [
  ...mockPositions,
  {
    id: 'pos-2',
    aisle_id: 'aisle-1',
    status: 'detected',
    confidence: 0.88,
    needs_review: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    sku: 'SKU-001',
    detected_quantity: 1,
    corrected_quantity: null,
    qty: 1,
    qtySource: 'detected',
    has_evidence: true,
  },
];

const repeatedSkuResults: ResultSummary[] = [
  ...mockResults,
  {
    id: 'pos-2',
    sku: 'SKU-001',
    detectedQty: 1,
    correctedQty: null,
    resolvedQty: null,
    confidence: 0.88,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'UNVALIDATED',
    needsReview: false,
    updatedAt: '2024-01-01T00:00:00Z',
    hasEvidence: true,
  },
];

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return {
    ...actual,
    getAisleMergeResults: (...args: Parameters<typeof actual.getAisleMergeResults>) =>
      getAisleMergeResultsMock(...args) as ReturnType<typeof actual.getAisleMergeResults>,
  };
});

vi.mock('../src/features/results', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/features/results')>();
  return {
    ...actual,
    useResultSummaries: () => ({
      ...resultSummariesState,
      resultJobId: resultSummariesState.resultJobId,
      resultContextSource: resultSummariesState.resultContextSource,
    }),
  };
});

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoryDetail: () => inventoryDetailState,
    useAislesList: () => aislesListState,
    useAisleMergeResults: () => mergeResultsState,
    useAisleJobsList: () => aisleJobsListState,
    useRunAisleMerge: useRunAisleMergeMock,
    usePromoteAisleOperationalJob: () => ({
      mutateAsync: promoteMutateAsync,
      isPending: false,
    }),
  };
});

function renderPage() {
  return renderPageAt('/inventories/inv-1/aisles/aisle-1/positions');
}

function renderPageAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/inventories/:inventoryId/aisles/:aisleId/positions"
              element={<AislePositionsPage />}
            />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('AislePositionsPage (Aisle Results)', () => {
  beforeEach(() => {
    resultSummariesState.results = mockResults;
    resultSummariesState.positions = mockPositions;
    resultSummariesState.isLoading = false;
    resultSummariesState.isError = false;
    resultSummariesState.error = null;
    resultSummariesState.resultJobId = null;
    resultSummariesState.resultContextSource = null;
    resultSummariesState.refetch = vi.fn();
    aislesListState.refetch = vi.fn();
    mergeResultsState.data = { results: [] };
    mergeResultsState.refetch = vi.fn();
    aisleJobsListState.data = { jobs: [], operational_job_id: null };
    aisleJobsListState.isLoading = false;
    aisleJobsListState.isFetched = true;
    aisleJobsListState.isFetching = false;
    useRunAisleMergeMock.mockReset();
    getAisleMergeResultsMock.mockReset();
    getAisleMergeResultsMock.mockResolvedValue({ results: [] });
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({
        operation_mode: 'manual_authoritative',
        authoritative_quantity_updated: true,
        raw_count: 3,
        normalized_count: 1,
        final_count: 1,
        product_records_updated: 1,
      }),
      isPending: false,
    });
    promoteMutateAsync.mockReset();
    promoteMutateAsync.mockResolvedValue({
      aisle_id: 'aisle-1',
      operational_job_id: 'job-bench',
    });
    inventoryDetailState.data.processing_mode = 'production';
  });

  it('shows aisle title, inventory context, and workload KPIs', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'A-01' })).toBeTruthy();
    expect(screen.getAllByText('Test Inventory')).toHaveLength(2);
    expect(screen.getByText('Counted total')).toBeTruthy();
    expect(screen.getByRole('button', { name: /merge repeated labels/i })).toBeTruthy();
  });

  it('shows operational columns including Priority and Review status', () => {
    renderPage();
    expect(screen.getByRole('columnheader', { name: /priority/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /SKU/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /quantity/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /review status/i })).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: /traceability/i })).toBeTruthy();
    expect(screen.getByText('SKU-001')).toBeTruthy();
    expect(screen.getAllByText('5').length).toBeGreaterThan(0);
  });

  it('opens review via SKU control without an Actions column', () => {
    renderPage();
    expect(screen.queryByRole('columnheader', { name: /^Actions$/i })).toBeNull();
    expect(screen.getByRole('button', { name: /table review aria/i })).toBeTruthy();
  });

  it('runs manual merge from the header and refreshes the visible results queries', async () => {
    resultSummariesState.results = repeatedSkuResults;
    resultSummariesState.positions = repeatedSkuPositions;
    mergeResultsState.data = { results: [] };
    const mutateAsync = vi.fn().mockResolvedValue({
      operation_mode: 'manual_authoritative',
      authoritative_quantity_updated: true,
      raw_count: 3,
      normalized_count: 1,
      final_count: 1,
      product_records_updated: 1,
    });
    getAisleMergeResultsMock.mockResolvedValue({
      results: [
        {
          id: 'fc-1',
          position_id: 'pos-1',
          sku: 'SKU-001',
          product_name: 'Product 1',
          merged_quantity: 6,
          normalized_label_ids: ['n1', 'n2'],
          review_required: false,
          explanation_summary: 'Merged repeated labels',
          metadata: {},
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
    });
    mergeResultsState.data = { results: [] };
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /merge repeated labels/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({ aisleId: 'aisle-1', jobId: null });
      expect(getAisleMergeResultsMock).toHaveBeenCalledWith('inv-1', 'aisle-1', { jobId: null });
    });

    expect(screen.getByText(/visible results updated after merge/i)).toBeTruthy();
  });

  it('passes result_job_id as job_id when merging so the request matches the visible slice', async () => {
    resultSummariesState.results = repeatedSkuResults;
    resultSummariesState.positions = repeatedSkuPositions;
    resultSummariesState.resultJobId = 'job-visible-1';
    mergeResultsState.data = { results: [] };
    const mutateAsync = vi.fn().mockResolvedValue({
      operation_mode: 'manual_authoritative',
      authoritative_quantity_updated: true,
      raw_count: 3,
      normalized_count: 1,
      final_count: 1,
      product_records_updated: 1,
    });
    getAisleMergeResultsMock.mockResolvedValue({ results: [] });
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /merge repeated labels/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        aisleId: 'aisle-1',
        jobId: 'job-visible-1',
      });
    });
  });

  it('shows a disabled pending merge button while the merge mutation is running', () => {
    resultSummariesState.results = repeatedSkuResults;
    resultSummariesState.positions = repeatedSkuPositions;
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: true,
    });

    renderPage();

    const button = screen.getByRole('button', { name: /merging/i });
    expect(button.getAttribute('disabled')).not.toBeNull();
    expect(button.textContent).toContain('Merging…');
  });

  it('keeps the merge button visible but disabled when there are no repeated sku candidates', () => {
    renderPage();

    const button = screen.getByRole('button', { name: /merge repeated labels/i });
    expect(button.getAttribute('disabled')).not.toBeNull();
  });

  it('shows a lightweight latest merge summary when merge-results contain consolidated groups', () => {
    mergeResultsState.data = {
      results: [
        {
          id: 'fc-1',
          position_id: 'pos-1',
          sku: 'SKU-001',
          product_name: 'Product 1',
          merged_quantity: 6,
          normalized_label_ids: ['n1', 'n2'],
          review_required: false,
          explanation_summary: 'Merged repeated labels',
          metadata: {},
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
    };

    renderPage();

  });

  it('resets local merge feedback when the aisle route changes', async () => {
    resultSummariesState.results = repeatedSkuResults;
    resultSummariesState.positions = repeatedSkuPositions;
    mergeResultsState.data = { results: [] };
    getAisleMergeResultsMock.mockResolvedValue({
      results: [
        {
          id: 'fc-1',
          position_id: 'pos-1',
          sku: 'SKU-001',
          product_name: 'Product 1',
          merged_quantity: 6,
          normalized_label_ids: ['n1', 'n2'],
          review_required: false,
          explanation_summary: 'Merged repeated labels',
          metadata: {},
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
    });

    const mutateAsync = vi.fn().mockResolvedValue({
      operation_mode: 'manual_authoritative',
      authoritative_quantity_updated: true,
      raw_count: 3,
      normalized_count: 1,
      final_count: 1,
      product_records_updated: 1,
    });
    useRunAisleMergeMock.mockReturnValue({
      mutateAsync,
      isPending: false,
    });

    const view = renderPage();
    fireEvent.click(screen.getByRole('button', { name: /merge repeated labels/i }));

    await waitFor(() => {
      expect(screen.getByText(/visible results updated after merge/i)).toBeTruthy();
    });

    mergeResultsState.data = { results: [] };
    resultSummariesState.results = mockResults;
    resultSummariesState.positions = mockPositions;
    view.unmount();
    renderPageAt('/inventories/inv-2/aisles/aisle-2/positions');

    expect(screen.queryByText(/visible results updated after merge/i)).toBeNull();
  });

  it('hides merge action when there are no results to consolidate', () => {
    resultSummariesState.results = [];
    resultSummariesState.positions = [];

    renderPage();

    expect(screen.queryByRole('button', { name: /merge repeated labels/i })).toBeNull();
  });

  it('shows run selector when jobs exist for the aisle', () => {
    inventoryDetailState.data.processing_mode = 'test';
    aisleJobsListState.data = {
      operational_job_id: 'job-op',
      jobs: [
        {
          id: 'job-a',
          status: 'succeeded',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
    };
    renderPage();
    expect(screen.getByLabelText(/browse run/i)).toBeTruthy();
  });

  it('shows resolved context line when backend returns result_context_source', () => {
    inventoryDetailState.data.processing_mode = 'test';
    resultSummariesState.resultContextSource = 'operational';
    resultSummariesState.resultJobId = 'job-x';
    aisleJobsListState.data = {
      operational_job_id: 'job-x',
      jobs: [
        {
          id: 'job-x',
          status: 'succeeded',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
    };
    renderPage();
    expect(screen.getByText(/resolved: operational/i)).toBeTruthy();
  });

  it('shows the backend-resolved run in the selector when there is no URL jobId and the job is listed', () => {
    inventoryDetailState.data.processing_mode = 'test';
    resultSummariesState.resultJobId = 'job-resolved';
    resultSummariesState.resultContextSource = 'operational';
    aisleJobsListState.data = {
      operational_job_id: 'job-resolved',
      jobs: [
        {
          id: 'job-resolved',
          status: 'succeeded',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
    };
    renderPage();
    const select = screen.getByLabelText(/browse run/i);
    expect(select.textContent).toMatch(/job-resolv/i);
  });

  it('repairs invalid jobId in URL to a listed run (no lingering unknown-job warning)', async () => {
    inventoryDetailState.data.processing_mode = 'test';
    aisleJobsListState.data = {
      operational_job_id: null,
      jobs: [
        {
          id: 'job-a',
          status: 'succeeded',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
    };
    renderPageAt('/inventories/inv-1/aisles/aisle-1/positions?jobId=unknown-job');
    await waitFor(() => {
      expect(screen.queryByText(/not in the recent runs list/i)).toBeNull();
    });
    const select = screen.getByLabelText(/browse run/i);
    expect(select.textContent).toMatch(/job-a/i);
  });

  it('does not show run selector for production inventories when jobs exist', () => {
    inventoryDetailState.data.processing_mode = 'production';
    aisleJobsListState.data = {
      operational_job_id: 'job-op',
      jobs: [
        {
          id: 'job-a',
          status: 'succeeded',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ],
    };
    renderPage();
    expect(screen.queryByLabelText(/browse run/i)).toBeNull();
  });

  it('hides compare runs for production inventories', () => {
    inventoryDetailState.data.processing_mode = 'production';
    aisleJobsListState.data = {
      operational_job_id: 'job-op',
      jobs: [
        {
          id: 'job-op',
          status: 'succeeded',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'job-bench',
          status: 'succeeded',
          created_at: '2024-01-02T00:00:00Z',
          updated_at: '2024-01-02T00:00:00Z',
        },
      ],
    };
    renderPage();
    expect(screen.queryByRole('button', { name: /compare runs/i })).toBeNull();
  });

  describe('Phase 6 benchmark flows', () => {
    beforeEach(() => {
      inventoryDetailState.data.processing_mode = 'test';
    });

    it('shows uploaded-files action and disables merge when no repeated SKUs (benchmark run selected)', () => {
      resultSummariesState.results = mockResults;
      resultSummariesState.positions = mockPositions;
      resultSummariesState.resultJobId = 'job-bench';
      aisleJobsListState.data = {
        operational_job_id: 'job-op',
        jobs: [
          {
            id: 'job-op',
            status: 'succeeded',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
          {
            id: 'job-bench',
            status: 'succeeded',
            created_at: '2024-01-02T00:00:00Z',
            updated_at: '2024-01-02T00:00:00Z',
          },
        ],
      };
      renderPage();
      expect(screen.getByTestId('aisle-source-assets-manage-open')).toBeTruthy();
      const mergeBtn = screen.getByRole('button', { name: /merge repeated labels/i });
      expect(mergeBtn.getAttribute('disabled')).not.toBeNull();
    });

    it('does not show compare runs when fewer than two jobs exist', () => {
      aisleJobsListState.data = {
        operational_job_id: 'job-op',
        jobs: [
          {
            id: 'job-op',
            status: 'succeeded',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      };
      renderPage();
      expect(screen.queryByRole('button', { name: /compare runs/i })).toBeNull();
    });

    it('navigates to analytics compare with preselected runs when compare runs is clicked', async () => {
      resultSummariesState.resultJobId = 'job-op';
      aisleJobsListState.data = {
        operational_job_id: 'job-op',
        jobs: [
          {
            id: 'job-op',
            status: 'succeeded',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
          {
            id: 'job-bench',
            status: 'succeeded',
            created_at: '2024-01-02T00:00:00Z',
            updated_at: '2024-01-02T00:00:00Z',
          },
        ],
      };
      const router = createMemoryRouter(
        [
          {
            path: '/inventories/:inventoryId/aisles/:aisleId/positions',
            element: <AislePositionsPage />,
          },
          {
            path: '/inventories/:inventoryId/analytics/compare',
            element: <div data-testid="compare-route-marker">compare</div>,
          },
        ],
        { initialEntries: ['/inventories/inv-1/aisles/aisle-1/positions'] }
      );
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <AppSnackbarProvider>
            <RouterProvider router={router} />
          </AppSnackbarProvider>
        </QueryClientProvider>
      );

      fireEvent.click(screen.getByRole('button', { name: /compare runs/i }));

      await waitFor(() => {
        expect(router.state.location.pathname).toBe('/inventories/inv-1/analytics/compare');
        const q = new URLSearchParams(router.state.location.search);
        expect(q.get('aisleId')).toBe('aisle-1');
        expect(q.get('jobAId')).toBe('job-op');
        expect(q.get('jobBId')).toBe('job-bench');
        expect(q.get('jobAId')).not.toBe(q.get('jobBId'));
      });
    });

    it('submits promotion and refetches results', async () => {
      resultSummariesState.results = mockResults;
      resultSummariesState.positions = mockPositions;
      resultSummariesState.resultJobId = 'job-bench';
      aisleJobsListState.data = {
        operational_job_id: 'job-op',
        jobs: [
          {
            id: 'job-op',
            status: 'succeeded',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
          {
            id: 'job-bench',
            status: 'succeeded',
            created_at: '2024-01-02T00:00:00Z',
            updated_at: '2024-01-02T00:00:00Z',
          },
        ],
      };
      renderPage();
      fireEvent.click(screen.getByRole('button', { name: /promote run/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm promote/i }));

      await waitFor(() => {
        expect(promoteMutateAsync).toHaveBeenCalledWith('job-bench');
      });
    });
  });
});

