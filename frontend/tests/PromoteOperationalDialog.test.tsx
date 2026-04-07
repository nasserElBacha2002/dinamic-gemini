/**
 * Phase 6 — promote operational pointer (no automatic correction transfer).
 */

import React from 'react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import PromoteOperationalDialog from '../src/features/benchmark/PromoteOperationalDialog';
import type { JobSummary } from '../src/api/types';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

describe('PromoteOperationalDialog', () => {
  const jobs: JobSummary[] = [
    {
      id: 'job-operational-xx',
      status: 'succeeded',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      is_operational: true,
      provider_name: 'prov-a',
      prompt_key: 'prompt-a',
    },
    {
      id: 'job-benchmark-yy',
      status: 'succeeded',
      created_at: '2024-01-02T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
      is_operational: false,
      provider_name: 'prov-b',
      prompt_key: 'prompt-b',
    },
    {
      id: 'job-failed-zz',
      status: 'failed',
      created_at: '2024-01-03T00:00:00Z',
      updated_at: '2024-01-03T00:00:00Z',
      is_operational: false,
    },
  ];

  it('lists only succeeded runs that are not already operational', async () => {
    render(
      <WithTheme>
        <PromoteOperationalDialog
          open
          onClose={() => {}}
          jobs={jobs}
          operationalJobId="job-operational-xx"
          promoteJobId="job-benchmark-yy"
          onPromoteJobIdChange={() => {}}
          onConfirm={() => {}}
          isPending={false}
        />
      </WithTheme>
    );

    const combo = screen.getByRole('combobox', { name: /succeeded run/i });
    fireEvent.mouseDown(combo);
    const list = await screen.findByRole('listbox');
    const opts = within(list).getAllByRole('option');
    expect(opts).toHaveLength(1);
    expect(opts[0].textContent).toMatch(/job-benchmar/i);
    expect(opts[0].textContent).toMatch(/prov-b/i);
  });

  it('submits via onConfirm', () => {
    const onConfirm = vi.fn();
    render(
      <WithTheme>
        <PromoteOperationalDialog
          open
          onClose={() => {}}
          jobs={jobs}
          operationalJobId="job-operational-xx"
          promoteJobId="job-benchmark-yy"
          onPromoteJobIdChange={() => {}}
          onConfirm={onConfirm}
          isPending={false}
        />
      </WithTheme>
    );

    fireEvent.click(screen.getByRole('button', { name: /confirm promote/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('clarifies pointer update and lack of automatic correction copy', () => {
    render(
      <WithTheme>
        <PromoteOperationalDialog
          open
          onClose={() => {}}
          jobs={jobs}
          operationalJobId="job-operational-xx"
          promoteJobId="job-benchmark-yy"
          onPromoteJobIdChange={() => {}}
          onConfirm={() => {}}
          isPending={false}
        />
      </WithTheme>
    );

    expect(screen.getByText(/operational slice/i)).toBeInTheDocument();
    expect(screen.getByText(/not copied automatically/i)).toBeInTheDocument();
  });
});
