import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AisleObservabilityWorkspace from '../src/components/AisleObservabilityWorkspace';
import { AppSnackbarProvider } from '../src/components/ui';
import * as capabilitiesHook from '../src/features/processing/hooks/useProcessingObservabilityCapabilities';

vi.mock('../src/features/processing', () => ({
  ProcessingWorkspace: () => <div data-testid="processing-workspace-stub">processing</div>,
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useAisleExecutionLog: () => ({ data: null, isLoading: false, isFetching: false, refetch: vi.fn() }),
    useAisleJobsList: () => ({ data: { jobs: [{ id: 'job-1', status: 'succeeded' }] }, isLoading: false, isFetching: false, refetch: vi.fn() }),
    useAisleJobDetail: () => ({ data: { id: 'job-1', status: 'succeeded' }, isLoading: false, isFetching: false, error: null, refetch: vi.fn() }),
    useExecutionLog: () => ({ data: null, isLoading: false, isFetching: false, refetch: vi.fn() }),
    useCancelAisleJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useRetryAisleJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
  };
});

vi.mock('../src/features/auth', () => ({
  useAuth: () => ({ user: { role: 'operator' } }),
}));

vi.mock('../src/features/executionLogs/hooks/useExecutionLogDownloads', () => ({
  useExecutionLogDownloads: () => ({
    downloadMergedExecutionLog: vi.fn(),
    downloadJobExecutionLog: vi.fn(),
    isDownloadingMerged: false,
    isDownloadingJobLog: false,
    clearError: vi.fn(),
  }),
}));

function wrap(initialEntry = '/?jobId=job-1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AppSnackbarProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <AisleObservabilityWorkspace
            inventoryId="inv-1"
            aisleId="aisle-1"
            aisleCode="A-01"
            initialSelectedJobId="job-1"
            active
          />
        </MemoryRouter>
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('AisleObservabilityWorkspace processing tab', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('hides processing tab when feature flag is disabled', () => {
    vi.spyOn(capabilitiesHook, 'useProcessingObservabilityCapabilities').mockReturnValue({
      processing_observability_enabled: false,
      source: 'fallback',
      isLoading: false,
      isError: false,
    });

    wrap();
    expect(screen.queryByTestId('obs-tab-processing')).not.toBeInTheDocument();
  });

  it('shows processing tab when feature flag is enabled', () => {
    vi.spyOn(capabilitiesHook, 'useProcessingObservabilityCapabilities').mockReturnValue({
      processing_observability_enabled: true,
      source: 'backend',
      isLoading: false,
      isError: false,
    });

    wrap('/?jobId=job-1&tab=procesamiento');
    expect(screen.getByTestId('obs-tab-processing')).toBeInTheDocument();
    expect(screen.getByTestId('processing-workspace-stub')).toBeInTheDocument();
  });
});
