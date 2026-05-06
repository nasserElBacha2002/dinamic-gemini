import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AisleRunSelector from '../src/features/results/components/AisleRunSelector';
import type { JobSummary } from '../src/api/types';

describe('AisleRunSelector', () => {
  it('shows only concrete runs (no synthetic default row) and labels operational vs benchmark', () => {
    const jobs: JobSummary[] = [
      {
        id: 'job-op',
        status: 'succeeded',
        created_at: '2026-01-01T12:00:00Z',
        updated_at: '2026-01-01T12:00:00Z',
        provider_name: 'openai',
        model_name: 'gpt',
        prompt_key: 'global_v21',
        prompt_version: 'global_v21@v1',
        is_operational: true,
      },
      {
        id: 'job-bench-1',
        status: 'succeeded',
        created_at: '2026-01-02T12:00:00Z',
        updated_at: '2026-01-02T12:00:00Z',
        provider_name: 'openai',
        model_name: 'gpt',
        prompt_key: 'global_v21',
        prompt_version: 'global_v21@v1',
        is_operational: false,
      },
    ];
    const onChange = vi.fn();
    render(
      <AisleRunSelector operationalJobId="job-op" jobs={jobs} valueJobId="job-op" onChange={onChange} />
    );
    fireEvent.mouseDown(screen.getByRole('combobox'));
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveAttribute('data-value', 'job-op');
    expect(options[1]).toHaveAttribute('data-value', 'job-bench-1');
    expect(options[0].textContent).toMatch(/operativo|operational/i);
    expect(options[1].textContent).toMatch(/referencia|benchmark/i);
  });
});
