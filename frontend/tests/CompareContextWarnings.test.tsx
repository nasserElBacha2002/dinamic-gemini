import '@testing-library/jest-dom/vitest';
import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import CompareContextWarnings from '../src/features/analytics/compare/components/CompareContextWarnings';
import type { AisleBenchmarkCompareManyResponse } from '../src/api/types';

const minimalData: AisleBenchmarkCompareManyResponse = {
  inventory_id: 'inv-1',
  aisle_id: 'aisle-1',
  workflow: 'benchmark_compare_many',
  read_only: true,
  baseline_job_id: 'job-1',
  jobs: [],
  comparisons: [],
  summary: {
    job_count: 0,
    baseline_job_id: 'job-1',
    max_total_quantity: 0,
    min_total_quantity: 0,
    max_needs_review: 0,
    min_needs_review: 0,
    max_consolidated_positions: 0,
    min_consolidated_positions: 0,
    max_unknown_internal_code_count: 0,
    min_unknown_internal_code_count: 0,
  },
  raw_fetch_truncated: [],
};

describe('CompareContextWarnings', () => {
  it('shows compact bullets and more-notes control in embedded mode', () => {
    render(<CompareContextWarnings data={minimalData} compact />);
    expect(screen.getByTestId('compare-benchmark-context-warnings')).toHaveAttribute('data-compact', 'true');
    expect(screen.getByText(/no recomienda automáticamente|does not automatically recommend/i)).toBeInTheDocument();
    expect(screen.queryByText(/mismo pasillo|same aisle/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('compare-benchmark-context-more-notes'));
    expect(screen.getByText(/mismo pasillo|same aisle/i)).toBeInTheDocument();
  });
});
