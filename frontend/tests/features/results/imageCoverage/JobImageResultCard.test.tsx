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

  it('hides add-result for positioning-label assets', () => {
    render(
      <JobImageResultCard
        item={makeItem({
          original_filename: 'pasillo01.jpg',
          is_product_candidate: false,
          excluded_from_uncounted: true,
          operational_role: 'POSITION_LABEL_RESOLVED',
        })}
        onAddResult={vi.fn()}
      />
    );

    expect(screen.queryByTestId('job-image-add-manual-result')).not.toBeInTheDocument();
    expect(screen.getByTestId('job-image-result-card')).toHaveAttribute(
      'data-operational-role',
      'POSITION_LABEL_RESOLVED',
    );
  });

  it('renders detected_products list and with-result chip when has_result', () => {
    render(
      <JobImageResultCard
        item={makeItem({
          has_result: true,
          result_count: 2,
          processing_status: 'processed_with_result',
          detected_products: [
            {
              product_record_id: 'pr-1',
              position_id: 'pos-1',
              sku: 'SKU-A',
              detected_quantity: 4,
              label_id: 'A1B2C3D4E5',
            },
            {
              product_record_id: 'pr-2',
              position_id: 'pos-2',
              sku: 'SKU-B',
              detected_quantity: 1,
              label_id: null,
            },
          ],
        })}
        onAddResult={vi.fn()}
      />
    );

    expect(screen.getByTestId('job-image-result-card')).toHaveAttribute('data-has-result', 'true');
    expect(screen.getByTestId('job-image-with-result-badge')).toBeInTheDocument();
    expect(screen.getByTestId('job-image-detected-products')).toBeInTheDocument();
    const rows = screen.getAllByTestId('job-image-detected-product');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('✓ SKU-A × 4 — A1B2C3D4E5');
    expect(rows[1]).toHaveTextContent('✓ SKU-B × 1');
  });
});
