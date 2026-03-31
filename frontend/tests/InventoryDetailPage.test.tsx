import '@testing-library/jest-dom/vitest';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import InventoryDetail from '../src/pages/InventoryDetail';
import { AppSnackbarProvider } from '../src/components/ui';

const { useInventoryVisualReferencesMock } = vi.hoisted(() => ({
  useInventoryVisualReferencesMock: vi.fn(),
}));
const { useUploadInventoryVisualReferencesMock } = vi.hoisted(() => ({
  useUploadInventoryVisualReferencesMock: vi.fn(),
}));
const { useDeleteInventoryVisualReferenceMock } = vi.hoisted(() => ({
  useDeleteInventoryVisualReferenceMock: vi.fn(),
}));
const { useReplaceInventoryVisualReferenceMock } = vi.hoisted(() => ({
  useReplaceInventoryVisualReferenceMock: vi.fn(),
}));
const { useExecutionLogMock } = vi.hoisted(() => ({
  useExecutionLogMock: vi.fn(),
}));
const { useAisleJobDetailMock } = vi.hoisted(() => ({
  useAisleJobDetailMock: vi.fn(),
}));
const { useAislesListMock } = vi.hoisted(() => ({
  useAislesListMock: vi.fn(),
}));
const { useCancelAisleJobMock } = vi.hoisted(() => ({
  useCancelAisleJobMock: vi.fn(),
}));
const { useRetryAisleJobMock } = vi.hoisted(() => ({
  useRetryAisleJobMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoryDetail: () => ({
      data: { id: 'inv-1', name: 'Inventory One', status: 'draft', created_at: '2024-01-01T00:00:00Z' },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }),
    useInventoryVisualReferences: useInventoryVisualReferencesMock,
    useAislesList: useAislesListMock,
    useExecutionLog: useExecutionLogMock,
    useAisleJobDetail: useAisleJobDetailMock,
    useCreateAisle: () => ({ mutateAsync: vi.fn() }),
    useStartAisleProcessing: () => ({ mutateAsync: vi.fn() }),
    useCancelAisleJob: useCancelAisleJobMock,
    useRetryAisleJob: useRetryAisleJobMock,
    useUploadAisleAssetsFlex: () => ({ mutateAsync: vi.fn() }),
    useUploadInventoryVisualReferences: useUploadInventoryVisualReferencesMock,
    useDeleteInventoryVisualReference: useDeleteInventoryVisualReferenceMock,
    useReplaceInventoryVisualReference: useReplaceInventoryVisualReferenceMock,
  };
});

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return {
    ...actual,
    exportInventoryResultsCsv: vi.fn(),
  };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={['/inventories/inv-1']}>
          <Routes>
            <Route path="/inventories/:inventoryId" element={<InventoryDetail />} />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('InventoryDetail', () => {
  beforeEach(() => {
    useInventoryVisualReferencesMock.mockReset();
    useAislesListMock.mockReset();
    useUploadInventoryVisualReferencesMock.mockReset();
    useDeleteInventoryVisualReferenceMock.mockReset();
    useReplaceInventoryVisualReferenceMock.mockReset();
    useExecutionLogMock.mockReset();
    useAisleJobDetailMock.mockReset();
    useCancelAisleJobMock.mockReset();
    useRetryAisleJobMock.mockReset();
    useUploadInventoryVisualReferencesMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useDeleteInventoryVisualReferenceMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useReplaceInventoryVisualReferenceMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useExecutionLogMock.mockReturnValue({
      data: { events: [] },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    useAisleJobDetailMock.mockReturnValue({
      data: null,
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useCancelAisleJobMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    });
    useRetryAisleJobMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    });
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'created',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            assets_count: 3,
            positions_count: 7,
            pending_review_positions_count: 1,
            latest_job: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it('keeps reference images lazy until the drawer opens', () => {
    useInventoryVisualReferencesMock.mockImplementation((_inventoryId, options) => ({
      data: {
        items: [
          {
            id: 'ref-1',
            inventory_id: 'inv-1',
            filename: 'front-pallet.jpg',
            mime_type: 'image/jpeg',
            file_size: 1024,
            created_at: '2024-01-02T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      enabled: options?.enabled,
    }));

    renderPage();

    expect(useInventoryVisualReferencesMock).toHaveBeenCalled();
    expect(useInventoryVisualReferencesMock.mock.calls[0]?.[1]).toMatchObject({ enabled: false });

    fireEvent.click(screen.getByRole('button', { name: 'Reference images' }));

    const lastCall = useInventoryVisualReferencesMock.mock.calls.at(-1);
    expect(lastCall?.[1]).toMatchObject({ enabled: true });
  });

  it('keeps the page focused on header and aisles, with a header action for reference images', () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: {
        items: [
          {
            id: 'ref-1',
            inventory_id: 'inv-1',
            filename: 'front-pallet.jpg',
            mime_type: 'image/jpeg',
            file_size: 1024,
            created_at: '2024-01-02T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));

    renderPage();

    expect(screen.getByRole('heading', { name: 'Inventory One' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reference images' })).toBeInTheDocument();
    expect(screen.getByText('Aisles')).toBeInTheDocument();

    expect(screen.queryByText('Total aisles')).not.toBeInTheDocument();
    expect(screen.queryByText('Review completion rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Activity')).not.toBeInTheDocument();
    expect(screen.queryByText('Logs summary')).not.toBeInTheDocument();
    expect(screen.queryByText('front-pallet.jpg')).not.toBeInTheDocument();
  });

  it('opens the reference images drawer and renders inventory reference data there', () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: {
        items: [
          {
            id: 'ref-1',
            inventory_id: 'inv-1',
            filename: 'front-pallet.jpg',
            mime_type: 'image/jpeg',
            file_size: 1024,
            created_at: '2024-01-02T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));

    renderPage();

    expect(screen.queryByText('front-pallet.jpg')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Reference images' }));

    expect(screen.getByRole('heading', { name: 'Reference images' })).toBeInTheDocument();
    expect(screen.getByText('front-pallet.jpg')).toBeInTheDocument();
    expect(
      screen.getByText(/reference images belong to this inventory and are used for future processing runs only\./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/^management$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /close reference images drawer/i })).toBeInTheDocument();
  });

  it('loads the execution log and job detail on demand without polling options', async () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'created',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            assets_count: 3,
            positions_count: 7,
            pending_review_positions_count: 1,
            latest_job: {
              id: 'job-1',
              status: 'succeeded',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              error_message: null,
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(useExecutionLogMock).toHaveBeenCalled();
    expect(useExecutionLogMock.mock.calls[0]?.[3]).toMatchObject({ enabled: false });
    expect(useAisleJobDetailMock).toHaveBeenCalled();
    expect(useAisleJobDetailMock.mock.calls[0]?.[3]).toMatchObject({ enabled: false });

    fireEvent.click(screen.getByRole('button', { name: /actions for aisle a-01/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /view job details/i }));

    await waitFor(() => {
      const lastCall = useExecutionLogMock.mock.calls.at(-1);
      const lastDetailCall = useAisleJobDetailMock.mock.calls.at(-1);
      expect(lastCall?.[3]).toMatchObject({ enabled: true });
      expect(lastDetailCall?.[3]).toMatchObject({ enabled: true });
      expect(screen.getByRole('button', { name: /^refresh$/i })).toBeInTheDocument();
    });
    expect(useExecutionLogMock.mock.calls.at(-1)?.[3]).not.toHaveProperty('refetchInterval');
  });

  it('renders job detail metadata, lineage, and execution log in the job dialog', async () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'processing',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            latest_job: {
              id: 'job-1',
              status: 'starting',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              attempt_count: 2,
              retry_of_job_id: 'job-0',
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useAisleJobDetailMock.mockReturnValue({
      data: {
        id: 'job-1',
        status: 'starting',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        started_at: '2024-01-01T00:00:00Z',
        finished_at: null,
        last_heartbeat_at: '2024-01-01T00:01:00Z',
        cancel_requested_at: null,
        current_stage: 'AnalysisStage',
        current_substep: 'provider_call',
        current_step_started_at: '2024-01-01T00:00:30Z',
        attempt_count: 2,
        retry_of_job_id: 'job-0',
        failure_code: null,
        failure_message: null,
        execution_id: 'exec-1',
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useExecutionLogMock.mockReturnValue({
      data: {
        events: [
          {
            ts: '2024-01-01T00:01:00Z',
            stage: 'AnalysisStage',
            level: 'info',
            message: 'stage.started',
            payload: { substep: 'provider_call' },
          },
        ],
      },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    fireEvent.click(screen.getByRole('button', { name: /actions for aisle a-01/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /view job details/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /job details/i })).toBeInTheDocument();
    });
    expect(screen.getAllByText('Attempt 2')).toHaveLength(2);
    expect(screen.getByText('Retry of job job-0')).toBeInTheDocument();
    expect(screen.getByText('Current stage')).toBeInTheDocument();
    expect(screen.getAllByText('AnalysisStage').length).toBeGreaterThan(0);
    expect(screen.getByText('Current step')).toBeInTheDocument();
    expect(screen.getByText('provider_call')).toBeInTheDocument();
    expect(screen.getByText('Execution ID')).toBeInTheDocument();
    expect(screen.getByText('exec-1')).toBeInTheDocument();
    expect(screen.getByText('stage.started')).toBeInTheDocument();
  });

  it('shows cancel for active jobs', async () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'processing',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            latest_job: {
              id: 'job-1',
              status: 'running',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useAisleJobDetailMock.mockReturnValue({
      data: {
        id: 'job-1',
        status: 'running',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /actions for aisle a-01/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /view job details/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel job/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /retry job/i })).not.toBeInTheDocument();
  });

  it('shows retry for retryable terminal jobs', async () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'failed',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            latest_job: {
              id: 'job-1',
              status: 'failed',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useAisleJobDetailMock.mockReturnValue({
      data: {
        id: 'job-1',
        status: 'failed',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /actions for aisle a-01/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /view job details/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry job/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /cancel job/i })).not.toBeInTheDocument();
  });

  it('cancel action triggers mutation and refreshes the job surface', async () => {
    const aislesRefetch = vi.fn().mockResolvedValue(undefined);
    const detailRefetch = vi.fn().mockResolvedValue(undefined);
    const logRefetch = vi.fn().mockResolvedValue(undefined);
    const cancelMutateAsync = vi.fn().mockResolvedValue({
      id: 'job-1',
      status: 'cancel_requested',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    });
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'processing',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            latest_job: {
              id: 'job-1',
              status: 'running',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: aislesRefetch,
    });
    useAisleJobDetailMock.mockReturnValue({
      data: {
        id: 'job-1',
        status: 'running',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: detailRefetch,
    });
    useExecutionLogMock.mockReturnValue({
      data: { events: [] },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: logRefetch,
    });
    useCancelAisleJobMock.mockReturnValue({
      mutateAsync: cancelMutateAsync,
      isPending: false,
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /actions for aisle a-01/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /view job details/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel job/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /cancel job/i }));

    await waitFor(() => {
      expect(cancelMutateAsync).toHaveBeenCalledWith({ aisleId: 'aisle-1', jobId: 'job-1' });
      expect(aislesRefetch).toHaveBeenCalled();
      expect(detailRefetch).toHaveBeenCalled();
      expect(logRefetch).toHaveBeenCalled();
    });
  });

  it('retry action triggers mutation and switches the dialog to the new attempt', async () => {
    const aislesRefetch = vi.fn().mockResolvedValue(undefined);
    const logRefetch = vi.fn().mockResolvedValue(undefined);
    const detailRefetch = vi.fn().mockResolvedValue(undefined);
    const retryMutateAsync = vi.fn().mockResolvedValue({
      id: 'job-2',
      status: 'starting',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      attempt_count: 2,
    });
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'failed',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            latest_job: {
              id: 'job-1',
              status: 'failed',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: aislesRefetch,
    });
    useAisleJobDetailMock.mockReturnValue({
      data: {
        id: 'job-1',
        status: 'failed',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: detailRefetch,
    });
    useExecutionLogMock.mockReturnValue({
      data: { events: [] },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: logRefetch,
    });
    useRetryAisleJobMock.mockReturnValue({
      mutateAsync: retryMutateAsync,
      isPending: false,
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /actions for aisle a-01/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /view job details/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry job/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /retry job/i }));

    await waitFor(() => {
      expect(retryMutateAsync).toHaveBeenCalledWith({ aisleId: 'aisle-1', jobId: 'job-1' });
      expect(aislesRefetch).toHaveBeenCalled();
      expect(logRefetch).toHaveBeenCalled();
      expect(detailRefetch).toHaveBeenCalled();
    });
    await waitFor(() => {
      const lastCall = useAisleJobDetailMock.mock.calls.at(-1);
      expect(lastCall?.[2]).toBe('job-2');
    });
  });

  it('renders compact reference usage summaries in the aisles table while keeping the log as the detail path', () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'processed',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            assets_count: 3,
            positions_count: 7,
            pending_review_positions_count: 1,
            latest_job: {
              id: 'job-1',
              status: 'succeeded',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              error_message: null,
              reference_usage: {
                resolved: true,
                resolved_count: 2,
                provider_consumed: true,
                provider_consumed_count: 2,
                reference_ids: ['ref-1', 'ref-2'],
                resolution_error: null,
              },
            },
          },
          {
            id: 'aisle-2',
            inventory_id: 'inv-1',
            code: 'A-02',
            status: 'failed',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            assets_count: 1,
            positions_count: 0,
            pending_review_positions_count: 0,
            latest_job: {
              id: 'job-2',
              status: 'failed',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              error_message: 'Reference resolution failed',
              reference_usage: {
                resolved: true,
                resolved_count: 1,
                provider_consumed: false,
                provider_consumed_count: 0,
                reference_ids: ['ref-missing'],
                resolution_error: 'visual reference ref-missing could not be resolved',
              },
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('Reference usage')).toBeInTheDocument();
    expect(screen.getByText('2 sent to Gemini')).toBeInTheDocument();
    expect(screen.getByText('2 prepared')).toBeInTheDocument();
    expect(screen.getByText('Reference setup failed')).toBeInTheDocument();
    expect(screen.getByText('1 prepared. Not sent to Gemini.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /actions for aisle/i })).toHaveLength(2);
  });

  it('shows a pending summary label when a queued or running job has no reference_usage yet', () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'queued',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            latest_job: {
              id: 'job-1',
              status: 'queued',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              error_message: null,
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('Pending run summary')).toBeInTheDocument();
  });

  it('shows summary unavailable when a completed job has no reference_usage payload', () => {
    useInventoryVisualReferencesMock.mockImplementation(() => ({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }));
    useAislesListMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'aisle-1',
            inventory_id: 'inv-1',
            code: 'A-01',
            status: 'failed',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            latest_job: {
              id: 'job-1',
              status: 'failed',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              error_message: 'failed',
            },
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('Summary unavailable')).toBeInTheDocument();
  });
});
