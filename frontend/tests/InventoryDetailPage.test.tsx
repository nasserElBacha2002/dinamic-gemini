import '@testing-library/jest-dom/vitest';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import InventoryDetail from '../src/pages/InventoryDetail';
import AisleObservabilityPage from '../src/pages/AisleObservabilityPage';
import { AppSnackbarProvider } from '../src/components/ui';
import type { ExecutionLogResponse } from '../src/api/types';
import { downloadAisleExecutionLogTxt, downloadExecutionLogTxt } from '../src/api/client';

const { useExecutionLogMock } = vi.hoisted(() => ({
  useExecutionLogMock: vi.fn(),
}));
const { useAisleExecutionLogMock } = vi.hoisted(() => ({
  useAisleExecutionLogMock: vi.fn(),
}));
const { useAisleJobDetailMock } = vi.hoisted(() => ({
  useAisleJobDetailMock: vi.fn(),
}));
const { useAislesListMock } = vi.hoisted(() => ({
  useAislesListMock: vi.fn(),
}));
const { useAisleJobsListMock } = vi.hoisted(() => ({
  useAisleJobsListMock: vi.fn(),
}));
const { useCancelAisleJobMock } = vi.hoisted(() => ({
  useCancelAisleJobMock: vi.fn(),
}));
const { useRetryAisleJobMock } = vi.hoisted(() => ({
  useRetryAisleJobMock: vi.fn(),
}));
const { useJobAuditabilityMock } = vi.hoisted(() => ({
  useJobAuditabilityMock: vi.fn(),
}));
const { processAisleMutateAsyncMock, useProcessingProviderOptionsMock } = vi.hoisted(() => ({
  processAisleMutateAsyncMock: vi.fn().mockResolvedValue({ job_id: 'job-new' }),
  useProcessingProviderOptionsMock: vi.fn(),
}));
const { inventoryDetailHookState } = vi.hoisted(() => ({
  inventoryDetailHookState: {
    data: {
      id: 'inv-1',
      name: 'Inventory One',
      status: 'draft',
      created_at: '2024-01-01T00:00:00Z',
      processing_mode: 'test' as 'production' | 'test',
    },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  },
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useInventoryDetail: () => inventoryDetailHookState,
    useAislesList: useAislesListMock,
    useAisleJobsList: useAisleJobsListMock,
    useExecutionLog: useExecutionLogMock,
    useAisleExecutionLog: useAisleExecutionLogMock,
    useAisleJobDetail: useAisleJobDetailMock,
    useCreateAisle: () => ({ mutateAsync: vi.fn() }),
    useProcessingProviderOptions: useProcessingProviderOptionsMock,
    useStartAisleProcessing: () => ({ mutateAsync: processAisleMutateAsyncMock }),
    useCancelAisleJob: useCancelAisleJobMock,
    useRetryAisleJob: useRetryAisleJobMock,
    useJobAuditability: useJobAuditabilityMock,
    useUploadAisleAssetsFlex: () => ({ mutateAsync: vi.fn() }),
  };
});

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return {
    ...actual,
    exportInventoryResultsCsv: vi.fn(),
    downloadExecutionLogTxt: vi.fn().mockResolvedValue(undefined),
    downloadAisleExecutionLogTxt: vi.fn().mockResolvedValue(undefined),
  };
});

function emptyExecutionLog(overrides: Partial<ExecutionLogResponse> = {}): ExecutionLogResponse {
  return {
    inventory_id: 'inv-1',
    aisle_id: 'aisle-1',
    requested_job_id: 'job-1',
    available_job_ids: ['job-1'],
    available_attempts: [],
    available_execution_ids: [],
    events: [],
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={['/inventories/inv-1']}>
          <Routes>
            <Route path="/inventories/:inventoryId" element={<InventoryDetail />} />
            <Route
              path="/inventories/:inventoryId/aisles/:aisleId/observability"
              element={<AisleObservabilityPage />}
            />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

function renderPageWithCompareRoute() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={['/inventories/inv-1']}>
          <Routes>
            <Route path="/inventories/:inventoryId" element={<InventoryDetail />} />
            <Route
              path="/inventories/:inventoryId/analytics/compare-many"
              element={<div data-testid="inventory-compare-route">compare</div>}
            />
          </Routes>
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('InventoryDetail', () => {
  beforeEach(() => {
    inventoryDetailHookState.data.processing_mode = 'test';
    useAislesListMock.mockReset();
    useExecutionLogMock.mockReset();
    useAisleExecutionLogMock.mockReset();
    useAisleJobsListMock.mockReset();
    useAisleJobDetailMock.mockReset();
    useCancelAisleJobMock.mockReset();
    useRetryAisleJobMock.mockReset();
    useJobAuditabilityMock.mockReset();
    processAisleMutateAsyncMock.mockReset();
    processAisleMutateAsyncMock.mockResolvedValue({ job_id: 'job-new' });
    useProcessingProviderOptionsMock.mockReset();
    useProcessingProviderOptionsMock.mockReturnValue({
      data: {
        default_provider_key: 'gemini',
        default_prompt_key: 'global_v21',
        prompt_profiles: [
          { key: 'global_v21', label: 'Prompt A', description: null },
          { key: 'global_v21_b', label: 'Prompt B', description: null },
        ],
        providers: [
          {
            key: 'gemini',
            label: 'Gemini',
            execution_mode: 'native',
            models: [{ id: 'gemini-2.0-flash-exp', label: 'gemini-2.0-flash-exp' }],
            default_model: 'gemini-2.0-flash-exp',
          },
          {
            key: 'openai',
            label: 'OpenAI',
            execution_mode: 'native',
            models: [{ id: 'gpt-4o-mini', label: 'gpt-4o-mini' }],
            default_model: 'gpt-4o-mini',
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
    });
    useExecutionLogMock.mockReturnValue({
      data: emptyExecutionLog(),
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    useAisleExecutionLogMock.mockReturnValue({
      data: undefined,
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
    useAisleJobsListMock.mockReturnValue({
      data: { jobs: [] },
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
    useJobAuditabilityMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
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

  it('does not expose legacy inventory-level reference image management on the inventory detail screen', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Inventory One' })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /visual refs title|referencias visuales/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/^(list title|pasillos)$/i)).toBeInTheDocument();

    expect(screen.queryByText('Total aisles')).not.toBeInTheDocument();
    expect(screen.queryByText('Review completion rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Activity')).not.toBeInTheDocument();
    expect(screen.queryByText('Logs summary')).not.toBeInTheDocument();
    expect(screen.queryByText(/Analytics & benchmarks/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('inventory-header-compare-runs')).toBeInTheDocument();
  });

  it('hides Compare runs header action for production inventories', () => {
    inventoryDetailHookState.data.processing_mode = 'production';
    renderPage();
    expect(screen.queryByTestId('inventory-header-compare-runs')).not.toBeInTheDocument();
    inventoryDetailHookState.data.processing_mode = 'test';
  });

  it('navigates to analytics compare from the Compare runs header button', async () => {
    renderPageWithCompareRoute();
    fireEvent.click(screen.getByTestId('inventory-header-compare-runs'));
    await waitFor(() => {
      expect(screen.getByTestId('inventory-compare-route')).toBeInTheDocument();
    });
  });

  it('loads observability queries only after opening the unified dialog (no polling)', async () => {
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'succeeded',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(useExecutionLogMock).not.toHaveBeenCalled();
    expect(useAisleJobDetailMock).not.toHaveBeenCalled();
    expect(useAisleExecutionLogMock).not.toHaveBeenCalled();
    expect(useAisleJobsListMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));

    await waitFor(() => {
      const lastLogCall = useExecutionLogMock.mock.calls.at(-1);
      const lastDetailCall = useAisleJobDetailMock.mock.calls.at(-1);
      expect(lastLogCall?.[3]).toMatchObject({ enabled: true });
      expect(lastDetailCall?.[3]).toMatchObject({ enabled: true });
      expect(screen.getByRole('button', { name: /^refresh$|^actualizar$/i })).toBeInTheDocument();
    });
    expect(useExecutionLogMock.mock.calls.at(-1)?.[3]).not.toHaveProperty('refetchInterval');
  });

  it('opens one observability dialog for merged aisle logs by default', async () => {
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
            positions_count: 0,
            pending_review_positions_count: 0,
            latest_job: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('aisle-observability-page')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /observabilidad del pasillo a-01/i })).toBeInTheDocument();
    });
    expect(screen.queryAllByRole('dialog')).toHaveLength(0);

    const scopeControl = screen.getByRole('combobox', { name: /log scope|alcance del log/i });
    expect(scopeControl.textContent).toMatch(/scope merged|consolidado/i);

    const lastAisleLog = useAisleExecutionLogMock.mock.calls.at(-1);
    expect(lastAisleLog?.[2]).toMatchObject({ enabled: true });
    const lastJobLog = useExecutionLogMock.mock.calls.at(-1);
    expect(lastJobLog?.[3]).toMatchObject({ enabled: false });
  });

  it('download actions call the correct execution-log endpoints from the unified dialog', async () => {
    vi.mocked(downloadAisleExecutionLogTxt).mockClear();
    vi.mocked(downloadExecutionLogTxt).mockClear();

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
            assets_count: 3,
            positions_count: 0,
            pending_review_positions_count: 0,
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'running',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
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
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /download merged log|descargar log consolidado/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /download merged log|descargar log consolidado/i }));
    await waitFor(() => {
      expect(vi.mocked(downloadAisleExecutionLogTxt)).toHaveBeenCalledWith('inv-1', 'aisle-1');
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: /download selected job log|descargar log de la ejecución seleccionada/i,
      }),
    );
    await waitFor(() => {
      expect(vi.mocked(downloadExecutionLogTxt)).toHaveBeenCalledWith('inv-1', 'aisle-1', 'job-1');
    });
  });

  it('switching log scope toggles which execution log query is active', async () => {
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
            assets_count: 3,
            positions_count: 0,
            pending_review_positions_count: 0,
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'running',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
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
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));

    await waitFor(() => {
      expect(useExecutionLogMock.mock.calls.at(-1)?.[3]).toMatchObject({ enabled: true });
    });

    fireEvent.mouseDown(screen.getByRole('combobox', { name: /log scope|alcance del log/i }));
    fireEvent.click(screen.getByRole('option', { name: /scope merged|consolidado/i }));

    await waitFor(() => {
      expect(useExecutionLogMock.mock.calls.at(-1)?.[3]).toMatchObject({ enabled: false });
    });
  });

  it('renders job metadata and execution log inside the unified observability dialog', async () => {
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'starting',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            attempt_count: 2,
            retry_of_job_id: 'job-0',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
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
      data: emptyExecutionLog({
        events: [
          {
            ts: '2024-01-01T00:01:00Z',
            stage: 'AnalysisStage',
            level: 'info',
            message: 'stage.started',
            payload: { substep: 'provider_call' },
            event_job_id: null,
            event_attempt: null,
            event_execution_id: null,
            is_requested_job_event: true,
          },
        ],
      }),
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('aisle-observability-page')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /observabilidad del pasillo a-01/i })).toBeInTheDocument();
    });
    expect(screen.getByText('job-0')).toBeInTheDocument();
    expect(screen.getAllByText('AnalysisStage').length).toBeGreaterThan(0);
    expect(screen.getByText('provider_call')).toBeInTheDocument();
    expect(screen.getByText('exec-1')).toBeInTheDocument();
    expect(screen.getByText('stage.started')).toBeInTheDocument();
  });

  it('shows Auditabilidad tab and auditability summary when tab is selected', async () => {
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
              status: 'succeeded',
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'succeeded',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useAisleJobDetailMock.mockReturnValue({
      data: {
        id: 'job-1',
        status: 'succeeded',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useExecutionLogMock.mockReturnValue({
      data: emptyExecutionLog(),
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    });
    useJobAuditabilityMock.mockReturnValue({
      data: {
        job_id: 'job-1',
        status: 'succeeded',
        target_type: 'aisle',
        target_id: 'aisle-1',
        created_at: '2024-01-01T00:00:00Z',
        started_at: null,
        finished_at: '2024-01-01T00:05:00Z',
        inventory_id: 'inv-1',
        aisle_id: 'aisle-1',
        client_id: 'client-x',
        client_supplier_id: 'cs-x',
        provider_name: 'gemini',
        model_name: 'm1',
        prompt_key: 'pk',
        prompt_version: 'pv',
        supplier_prompt_config_id: 'spc-audit',
        supplier_prompt_config_version: '3',
        supplier_prompt_fallback_used: false,
        supplier_prompt_fallback_reason: null,
        protected_prompt_contract_key: 'ppc',
        protected_prompt_contract_version: '1',
        effective_prompt_hash: 'hash-audit-panel',
        prompt_composition_available: true,
        reference_usage: null,
        supplier_reference_images_used: true,
        inventory_visual_references_used: null,
        reference_source: 'supplier_reference_images',
        reference_image_count: 1,
        reference_ids: ['r1'],
        warnings: [],
        metadata_sources: {
          job_row: true,
          result_json: true,
          aisle_join: true,
          inventory_join: true,
          hybrid_report: false,
          execution_log: false,
          run_audit_snapshot: false,
        },
        missing_metadata: ['hybrid_report', 'execution_log'],
        legacy_mode: false,
        cost_snapshot: null,
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('aisle-observability-page')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('tab', { name: /auditabilidad/i }));

    await waitFor(() => {
      expect(screen.getByTestId('job-auditability-panel')).toBeInTheDocument();
      expect(screen.getByText('hash-audit-panel')).toBeInTheDocument();
      expect(screen.getByText('spc-audit')).toBeInTheDocument();
      expect(screen.getByText('hybrid_report')).toBeInTheDocument();
      expect(screen.getByText('execution_log')).toBeInTheDocument();
    });
  });

  it('shows cancel for active jobs', async () => {
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'running',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
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
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel job|cancelar ejecución/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /retry job|reintentar ejecución/i })).not.toBeInTheDocument();
  });

  it('shows retry for retryable terminal jobs', async () => {
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'failed',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
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
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry job|reintentar ejecución/i })).toBeInTheDocument();
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-1',
            status: 'running',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
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
      refetch: detailRefetch,
    });
    useExecutionLogMock.mockReturnValue({
      data: emptyExecutionLog(),
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
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel job|cancelar ejecución/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /cancel job|cancelar ejecución/i }));

    await waitFor(() => {
      expect(cancelMutateAsync).toHaveBeenCalledWith({ aisleId: 'aisle-1', jobId: 'job-1' });
      expect(aislesRefetch).toHaveBeenCalled();
      expect(detailRefetch).toHaveBeenCalled();
      expect(logRefetch).toHaveBeenCalled();
    });
  });

  it('retry action triggers mutation and switches the dialog to the new attempt', async () => {
    const aislesRefetch = vi.fn().mockResolvedValue(undefined);
    const detailRefetch = vi.fn().mockResolvedValue(undefined);
    const retryMutateAsync = vi.fn().mockResolvedValue({
      id: 'job-2',
      status: 'starting',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      attempt_count: 2,
    });
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
    useAisleJobsListMock.mockReturnValue({
      data: {
        jobs: [
          {
            id: 'job-2',
            status: 'starting',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
            attempt_count: 2,
          },
          {
            id: 'job-1',
            status: 'failed',
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useAisleJobDetailMock.mockImplementation((_inv, _aisle, jobId) => ({
      data:
        jobId === 'job-2'
          ? {
              id: 'job-2',
              status: 'starting',
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-01-01T00:00:00Z',
              attempt_count: 2,
            }
          : {
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
    }));
    useExecutionLogMock.mockImplementation((_inv, _aisle, jobId) => ({
      data: emptyExecutionLog({ requested_job_id: jobId ?? 'job-1' }),
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    }));
    useRetryAisleJobMock.mockReturnValue({
      mutateAsync: retryMutateAsync,
      isPending: false,
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^view logs$|^ver logs$|^ver observabilidad$/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry job|reintentar ejecución/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /retry job|reintentar ejecución/i }));

    await waitFor(() => {
      expect(retryMutateAsync).toHaveBeenCalledWith({ aisleId: 'aisle-1', jobId: 'job-1' });
      expect(aislesRefetch).toHaveBeenCalled();
    });
    await waitFor(() => {
      const lastCall = useAisleJobDetailMock.mock.calls.at(-1);
      expect(lastCall?.[2]).toBe('job-2');
    });
  });

  it('renders compact reference usage summaries in the aisles table while keeping the log as the detail path', () => {
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

    expect(screen.getByText(/column reference usage|uso de referencias/i)).toBeInTheDocument();
    expect(screen.getByText('Sent many')).toBeInTheDocument();
    expect(screen.getByText('Prepared many')).toBeInTheDocument();
    expect(screen.getByText('Reference setup failed')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /row actions a11y|acciones del pasillo/i })).toHaveLength(2);
  });

  it('shows a pending summary label when a queued or running job has no reference_usage yet', () => {
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

  it('disables Process aisle when the aisle has no uploaded assets and shows helper text', async () => {
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
            assets_count: 0,
            positions_count: 0,
            pending_review_positions_count: 0,
            latest_job: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    const processItem = screen.getByRole('menuitem', { name: /process aisle|procesar pasillo/i });
    expect(processItem).toHaveAttribute('aria-disabled', 'true');
    expect(processItem.textContent).toMatch(/upload_need_image/i);
  });

  it('process dialog shows resolved default model id in the model placeholder option', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /process aisle|procesar pasillo/i }));
    expect(await screen.findByRole('heading', { name: /procesar pasillo a-01/i })).toBeInTheDocument();

    const modelSelect = screen.getByLabelText(/^model$|^modelo$/i, { selector: '[role="combobox"]' });
    fireEvent.mouseDown(modelSelect);
    expect(
      await screen.findByRole('option', { name: /usar modelo predeterminado \(gemini-2.0-flash-exp\)/i })
    ).toBeInTheDocument();
  });

  it('process dialog explains automatic prompt and does not show advanced prompt controls', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /process aisle|procesar pasillo/i }));
    const dialog = await screen.findByRole('dialog');
    const view = within(dialog);
    expect(view.getByText('Prompt utilizado')).toBeInTheDocument();
    expect(view.getByText(/instrucciones activas del proveedor asociado a este pasillo/i)).toBeInTheDocument();
    expect(view.queryByText(/opciones avanzadas/i)).not.toBeInTheDocument();
    expect(view.queryByText(/perfil base del prompt/i)).not.toBeInTheDocument();
    // Exact labels only: /prompt b/i would match "prompt base" in Spanish helper copy.
    expect(view.queryByText(/^Prompt A$/i)).not.toBeInTheDocument();
    expect(view.queryByText(/^Prompt B$/i)).not.toBeInTheDocument();
  });

  it('process aisle opens provider dialog and passes provider/model with default prompt key', async () => {
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /process aisle|procesar pasillo/i }));

    expect(await screen.findByRole('heading', { name: /procesar pasillo a-01/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/proveedor de ia/i)).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByLabelText(/proveedor de ia/i));
    const openaiOption = await screen.findByRole('option', { name: /openai/i });
    fireEvent.click(openaiOption);

    fireEvent.mouseDown(screen.getByLabelText(/^model$|^modelo$/i));
    fireEvent.click(await screen.findByRole('option', { name: /^gpt-4o-mini$/i }));

    fireEvent.click(screen.getByRole('button', { name: /^procesar$/i }));

    await waitFor(() => {
      expect(processAisleMutateAsyncMock).toHaveBeenCalledWith({
        aisleId: 'aisle-1',
        providerName: 'openai',
        modelName: 'gpt-4o-mini',
        promptKey: null,
      });
    });
  });

  it('production inventory starts aisle processing without opening the provider dialog', async () => {
    inventoryDetailHookState.data.processing_mode = 'production';
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /row actions a11y|acciones del pasillo/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /process aisle|procesar pasillo/i }));

    await waitFor(() => {
      expect(processAisleMutateAsyncMock).toHaveBeenCalledWith({
        aisleId: 'aisle-1',
        providerName: null,
        modelName: null,
        promptKey: null,
      });
    });
    expect(screen.queryByLabelText(/^provider$|^proveedor$/i)).toBeNull();
  });
});
