import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import JobObservabilityDiagnosticsPanel from '../src/components/JobObservabilityDiagnosticsPanel';
import { AppSnackbarProvider } from '../src/components/ui';
import type {
  ArtifactPreview,
  JobArtifactPage,
  JobErrorPage,
  JobRetryChain,
  JobTimelinePage,
} from '../src/api/types';

const getJobRetryChain = vi.fn<[], Promise<JobRetryChain>>();
const getJobArtifacts = vi.fn<[], Promise<JobArtifactPage>>();
const getJobTimeline = vi.fn<[], Promise<JobTimelinePage>>();
const getExecutionLogPage = vi.fn();
const getJobErrors = vi.fn<[], Promise<JobErrorPage>>();
const getJobHybridReport = vi.fn();
const getJobArtifactPreview = vi.fn<[], Promise<ArtifactPreview>>();

vi.mock('../src/api/jobsApi', () => ({
  getJobRetryChain: (...args: unknown[]) => getJobRetryChain(...(args as [])),
  getJobArtifacts: (...args: unknown[]) => getJobArtifacts(...(args as [])),
  getJobTimeline: (...args: unknown[]) => getJobTimeline(...(args as [])),
  getExecutionLogPage: (...args: unknown[]) => getExecutionLogPage(...(args as [])),
  getJobErrors: (...args: unknown[]) => getJobErrors(...(args as [])),
  getJobHybridReport: (...args: unknown[]) => getJobHybridReport(...(args as [])),
  getJobArtifactPreview: (...args: unknown[]) => getJobArtifactPreview(...(args as [])),
  downloadJobArtifact: vi.fn(),
}));

function Wrapper({ children }: { children: ReactNode }) {
  return <AppSnackbarProvider>{children}</AppSnackbarProvider>;
}

const emptyPage = { items: [], page: { next_cursor: null, has_more: false } };

function setupDefaultMocks() {
  getJobRetryChain.mockResolvedValue({
    root_job_id: 'job-1',
    selected_job_id: 'job-1',
    current_job_id: 'job-1',
    integrity: 'VALID',
    attempts: [],
  });
  getJobArtifacts.mockResolvedValue({ ...emptyPage, inputs_legacy_unverified: false });
  getJobTimeline.mockResolvedValue({ ...emptyPage });
  getExecutionLogPage.mockResolvedValue({ ...emptyPage, pagination_mode: 'incremental' });
  getJobErrors.mockResolvedValue({ ...emptyPage });
  getJobHybridReport.mockResolvedValue({});
}

describe('JobObservabilityDiagnosticsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the input snapshot warning when inputs_legacy_unverified is true', async () => {
    getJobArtifacts.mockResolvedValue({ ...emptyPage, inputs_legacy_unverified: true });

    render(
      <Wrapper>
        <JobObservabilityDiagnosticsPanel
          inventoryId="inv-1"
          aisleId="aisle-1"
          jobId="job-1"
          active
        />
      </Wrapper>
    );

    await waitFor(() =>
      expect(
        screen.getByText(
          'No fue posible guardar el snapshot auditable de los archivos utilizados. Los inputs mostrados pueden estar incompletos.'
        )
      ).toBeInTheDocument()
    );
  });

  it('shows a forked-chain warning and renders sibling attempts + edges', async () => {
    getJobRetryChain.mockResolvedValue({
      root_job_id: 'job-1',
      selected_job_id: 'job-1',
      current_job_id: 'job-2',
      integrity: 'FORKED',
      warnings: ['fork_at=job-1:children=[job-2,job-3]'],
      edges: [
        { from_job_id: 'job-1', to_job_id: 'job-2' },
        { from_job_id: 'job-1', to_job_id: 'job-3' },
      ],
      attempts: [
        {
          job_id: 'job-1',
          attempt_number: 1,
          status: 'failed',
          is_selected: true,
          is_current: false,
          is_successful: false,
        },
        {
          job_id: 'job-2',
          attempt_number: 2,
          status: 'succeeded',
          is_selected: false,
          is_current: true,
          is_successful: true,
        },
      ],
    });

    render(
      <Wrapper>
        <JobObservabilityDiagnosticsPanel
          inventoryId="inv-1"
          aisleId="aisle-1"
          jobId="job-1"
          active
        />
      </Wrapper>
    );

    await waitFor(() =>
      expect(
        screen.getByText(
          'La cadena de reintentos está bifurcada: se muestran todos los intentos conocidos, incluidas ramas alternativas.'
        )
      ).toBeInTheDocument()
    );
    expect(screen.getByText('job-1 → job-2')).toBeInTheDocument();
    expect(screen.getByText('job-1 → job-3')).toBeInTheDocument();
  });

  it('shows a load-more button for timeline when has_more is true and loads the next page', async () => {
    getJobTimeline.mockResolvedValueOnce({
      items: [
        {
          id: 'ev-1',
          job_id: 'job-1',
          event_type: 'STATUS_CHANGE',
          level: 'info',
          sequence: 1,
        },
      ],
      page: { next_cursor: 'cursor-2', has_more: true },
      pagination_mode: 'incremental',
      truncated: true,
    });
    getJobTimeline.mockResolvedValueOnce({
      items: [
        {
          id: 'ev-2',
          job_id: 'job-1',
          event_type: 'STATUS_CHANGE',
          level: 'info',
          sequence: 2,
        },
      ],
      page: { next_cursor: null, has_more: false },
    });

    render(
      <Wrapper>
        <JobObservabilityDiagnosticsPanel
          inventoryId="inv-1"
          aisleId="aisle-1"
          jobId="job-1"
          active
        />
      </Wrapper>
    );

    await waitFor(() => expect(getJobTimeline).toHaveBeenCalledTimes(1));
    const loadMoreButtons = await screen.findAllByRole('button', { name: 'Cargar más' });
    expect(loadMoreButtons.length).toBeGreaterThan(0);

    loadMoreButtons[0].click();

    await waitFor(() => expect(getJobTimeline).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(getJobTimeline).toHaveBeenLastCalledWith('inv-1', 'aisle-1', 'job-1', {
        cursor: 'cursor-2',
        limit: 50,
      })
    );
  });
});
