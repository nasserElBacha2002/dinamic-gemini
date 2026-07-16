/**
 * Job image coverage card — "sin resultado" / "con resultado" badges, nested results, add-result action.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import JobImageResultCard from '../../../../src/features/results/components/imageCoverage/JobImageResultCard';
import { useEvidenceImageLoad } from '../../../../src/features/results/hooks/useEvidenceImageLoad';
import type { JobImageResultItem, PositionSummary } from '../../../../src/api/types';

vi.mock('../../../../src/features/results/hooks/useEvidenceImageLoad', () => ({
  useEvidenceImageLoad: vi.fn(() => ({ status: 'idle' as const })),
}));

const mockUseEvidenceImageLoad = vi.mocked(useEvidenceImageLoad);

function makeItem(overrides?: Partial<JobImageResultItem>): JobImageResultItem {
  return {
    image_id: 'img-1',
    source_asset_id: 'asset-1',
    job_id: 'job-1',
    image_url: '/api/v3/inventories/inv-1/aisles/aisle-1/assets/asset-1/file?job_id=job-1',
    original_filename: 'IMG_0001.JPG',
    created_at: '2024-01-01T00:00:00Z',
    processing_status: 'processed_without_result',
    has_result: false,
    result_count: 0,
    results: [],
    ...overrides,
  };
}

function makePosition(overrides?: Partial<PositionSummary>): PositionSummary {
  return {
    id: 'pos-1',
    aisle_id: 'aisle-1',
    status: 'detected',
    position_code: 'P1',
    sku: 'SKU001',
    confidence: 0.9,
    needs_review: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    has_evidence: false,
    qty: 3,
    qtySource: 'detected',
    ...overrides,
  } as PositionSummary;
}

describe('JobImageResultCard', () => {
  it('renders the "sin resultado" badge and an add-result action when the image has no result', () => {
    mockUseEvidenceImageLoad.mockReturnValue({ status: 'idle' } as ReturnType<
      typeof useEvidenceImageLoad
    >);
    const onAddResult = vi.fn();
    render(
      <JobImageResultCard
        inventoryId="inv-1"
        aisleId="aisle-1"
        item={makeItem({ has_result: false, result_count: 0, results: [] })}
        onAddResult={onAddResult}
      />
    );

    expect(screen.getByTestId('job-image-without-result-badge')).toBeInTheDocument();
    expect(screen.getByTestId('job-image-without-result-badge')).toHaveTextContent(/sin resultado/i);
    expect(screen.queryByTestId('job-image-with-result-badge')).not.toBeInTheDocument();
    expect(screen.getByTestId('job-image-add-manual-result')).toBeInTheDocument();
    expect(screen.getByTestId('job-image-result-card')).toHaveAttribute('data-has-result', 'false');
  });

  it('renders the "con resultado" badge with count and hides the add-result action when covered', () => {
    mockUseEvidenceImageLoad.mockReturnValue({ status: 'idle' } as ReturnType<
      typeof useEvidenceImageLoad
    >);
    render(
      <JobImageResultCard
        inventoryId="inv-1"
        aisleId="aisle-1"
        item={makeItem({
          has_result: true,
          result_count: 1,
          results: [makePosition({ creation_source: 'automatic' })],
        })}
        onAddResult={vi.fn()}
      />
    );

    const badge = screen.getByTestId('job-image-with-result-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(/con resultado/i);
    expect(badge).toHaveTextContent('1');
    expect(screen.queryByTestId('job-image-without-result-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('job-image-add-manual-result')).not.toBeInTheDocument();
    expect(screen.getByTestId('job-image-result-card')).toHaveAttribute('data-has-result', 'true');
  });

  it('shows the "Carga manual" badge for manual results and "Automático" for automatic ones', () => {
    mockUseEvidenceImageLoad.mockReturnValue({ status: 'idle' } as ReturnType<
      typeof useEvidenceImageLoad
    >);
    render(
      <JobImageResultCard
        inventoryId="inv-1"
        aisleId="aisle-1"
        item={makeItem({
          has_result: true,
          result_count: 2,
          results: [
            makePosition({ id: 'pos-1', creation_source: 'automatic' }),
            makePosition({ id: 'pos-2', creation_source: 'manual' }),
          ],
        })}
        onAddResult={vi.fn()}
      />
    );

    expect(screen.getByTestId('job-image-result-creation-source-automatic')).toHaveTextContent(
      /automático/i
    );
    expect(screen.getByTestId('job-image-result-creation-source-manual')).toHaveTextContent(
      /carga manual/i
    );
  });
});
