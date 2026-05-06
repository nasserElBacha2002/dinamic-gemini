/**
 * Phase 6 — benchmark compare run picker (read-only path).
 */

import React from 'react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import CompareRunsDialog from '../src/features/benchmark/CompareRunsDialog';
import type { JobSummary } from '../src/api/types';

function WithTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}

const sampleJobs: JobSummary[] = [
  {
    id: 'job-aaaaaaaa',
    status: 'succeeded',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    is_operational: true,
  },
  {
    id: 'job-bbbbbbbb',
    status: 'succeeded',
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
    is_operational: false,
  },
];

describe('CompareRunsDialog', () => {
  it('disables Open compare when run A and B are the same', () => {
    const onConfirm = vi.fn();
    render(
      <WithTheme>
        <CompareRunsDialog
          open
          onClose={() => {}}
          jobs={sampleJobs}
          compareJobA="job-aaaaaaaa"
          compareJobB="job-aaaaaaaa"
          onCompareJobAChange={() => {}}
          onCompareJobBChange={() => {}}
          onConfirm={onConfirm}
        />
      </WithTheme>
    );

    const go = screen.getByRole('button', { name: /open compare/i });
    expect(go).toBeDisabled();
    fireEvent.click(go);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('calls onConfirm when two different runs are selected', () => {
    const onConfirm = vi.fn();
    render(
      <WithTheme>
        <CompareRunsDialog
          open
          onClose={() => {}}
          jobs={sampleJobs}
          compareJobA="job-aaaaaaaa"
          compareJobB="job-bbbbbbbb"
          onCompareJobAChange={() => {}}
          onCompareJobBChange={() => {}}
          onConfirm={onConfirm}
        />
      </WithTheme>
    );

    fireEvent.click(screen.getByRole('button', { name: /open compare/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('mentions read-only benchmark compare separate from operational analytics', () => {
    render(
      <WithTheme>
        <CompareRunsDialog
          open
          onClose={() => {}}
          jobs={sampleJobs}
          compareJobA="job-aaaaaaaa"
          compareJobB="job-bbbbbbbb"
          onCompareJobAChange={() => {}}
          onCompareJobBChange={() => {}}
          onConfirm={() => {}}
        />
      </WithTheme>
    );

    /** Copy comes from i18n (`benchmark.compare_readonly_explain`). */
    expect(screen.getByText(/Compare readonly explain|readonly/i)).toBeInTheDocument();
  });
});
