/**
 * Unmatched queue grid: filters out covered rows, no summary/filters/thumbnails, empty CTA.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import JobImageResultsGrid from '../../../../src/features/results/components/imageCoverage/JobImageResultsGrid';
import type { JobImageResultItem } from '../../../../src/api/types';

function makeItem(overrides?: Partial<JobImageResultItem>): JobImageResultItem {
  return {
    job_source_asset_id: 'jsa-1',
    source_asset_id: 'asset-1',
    job_id: 'job-1',
    image_url: '/api/v3/inventories/inv-1/aisles/aisle-1/assets/asset-1/file?job_id=job-1',
    original_filename: 'pending.jpg',
    created_at: '2024-01-01T00:00:00Z',
    position_order: 1,
    processing_status: 'processed_without_result',
    has_result: false,
    result_count: 0,
    automatic_result_count: 0,
    manual_result_count: 0,
    has_manual_result: false,
    results: [],
    ...overrides,
  };
}

describe('JobImageResultsGrid', () => {
  it('renders only unmatched rows and hides covered ones defensively', () => {
    render(
      <JobImageResultsGrid
        items={[
          makeItem({ job_source_asset_id: 'a', has_result: false, result_count: 0 }),
          makeItem({
            job_source_asset_id: 'b',
            source_asset_id: 'asset-2',
            original_filename: 'covered.jpg',
            has_result: true,
            result_count: 1,
          }),
        ]}
        isLoading={false}
        onAddResult={vi.fn()}
        page={1}
        pageSize={25}
        totalItems={1}
        pendingCount={1}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />
    );

    expect(screen.getByText('pending.jpg')).toBeInTheDocument();
    expect(screen.queryByText('covered.jpg')).not.toBeInTheDocument();
    expect(screen.queryByText(/total de imágenes/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^todas/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('shows defensive empty state with back-to-positions action', () => {
    const onBack = vi.fn();
    render(
      <JobImageResultsGrid
        items={[]}
        isLoading={false}
        onAddResult={vi.fn()}
        page={1}
        pageSize={25}
        totalItems={0}
        pendingCount={0}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
        onBackToPositions={onBack}
      />
    );

    expect(screen.getByTestId('job-image-results-empty')).toHaveTextContent(/no quedan imágenes sin contar/i);
    fireEvent.click(screen.getByTestId('job-image-back-to-positions'));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
