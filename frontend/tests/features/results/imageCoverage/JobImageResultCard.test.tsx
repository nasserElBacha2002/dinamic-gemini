/**
 * Unmatched-image queue row — order, filename, single status badge, add-result action.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import JobImageResultCard from '../../../../src/features/results/components/imageCoverage/JobImageResultCard';
import type { JobImageResultItem } from '../../../../src/api/types';

function makeItem(overrides?: Partial<JobImageResultItem>): JobImageResultItem {
  return {
    job_source_asset_id: 'jsa-1',
    source_asset_id: 'asset-1',
    job_id: 'job-1',
    image_url: '/api/v3/inventories/inv-1/aisles/aisle-1/assets/asset-1/file?job_id=job-1',
    original_filename: 'IMG_0001.JPG',
    created_at: '2024-01-01T00:00:00Z',
    position_order: 0,
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

describe('JobImageResultCard', () => {
  it('renders order, filename, single without-result badge, and add-result action', () => {
    const onAddResult = vi.fn();
    render(
      <JobImageResultCard item={makeItem({ position_order: 1 })} onAddResult={onAddResult} />
    );

    expect(screen.getByTestId('job-image-position-order')).toHaveTextContent('#2');
    expect(screen.getByText('IMG_0001.JPG')).toBeInTheDocument();
    expect(screen.getByTestId('job-image-without-result-badge')).toHaveTextContent(/sin resultado/i);
    expect(screen.queryByTestId('job-image-with-result-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('job-image-result-counts')).not.toBeInTheDocument();
    expect(screen.queryByTestId('job-image-result-creation-source-automatic')).not.toBeInTheDocument();
    expect(screen.getByTestId('job-image-add-manual-result')).toBeInTheDocument();
    expect(screen.getByTestId('job-image-result-card')).toHaveAttribute('data-has-result', 'false');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('shows processing-failed badge instead of without-result when status is failed', () => {
    render(
      <JobImageResultCard
        item={makeItem({ processing_status: 'failed' })}
        onAddResult={vi.fn()}
      />
    );

    expect(screen.getByTestId('job-image-failed-badge')).toHaveTextContent(/procesamiento fallido/i);
    expect(screen.queryByTestId('job-image-without-result-badge')).not.toBeInTheDocument();
    expect(screen.getByTestId('job-image-add-manual-result')).toBeInTheDocument();
  });
});
