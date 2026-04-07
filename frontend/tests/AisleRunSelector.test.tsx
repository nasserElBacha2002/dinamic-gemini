import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AisleRunSelector from '../src/features/results/components/AisleRunSelector';
import type { JobSummary } from '../src/api/types';

describe('AisleRunSelector', () => {
  it('does not claim latest-succeeded fallback in default row caption', async () => {
    const jobs: JobSummary[] = [
      {
        id: 'job-bench-1',
        status: 'succeeded',
        created_at: '2026-01-01T12:00:00Z',
        updated_at: '2026-01-01T12:00:00Z',
        provider_name: 'openai',
        model_name: 'gpt',
        prompt_key: 'global_v21',
        prompt_version: 'global_v21@v1',
        is_operational: false,
      },
    ];
    const onChange = vi.fn();
    render(
      <AisleRunSelector
        operationalJobId="job-op"
        jobs={jobs}
        valueJobId={null}
        onChange={onChange}
        urlPinned={false}
      />
    );
    fireEvent.mouseDown(screen.getByRole('combobox'));
    expect(screen.getAllByText(/operational_job_id when set, else legacy rows/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/latest-succeeded/i)).toBeNull();
  });
});
