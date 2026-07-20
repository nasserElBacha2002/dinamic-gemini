import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ProcessingAssetList from '../../../src/features/processing/ProcessingAssetList';
import type { AssetProcessingSummary } from '../../../src/api/types/processing';

function sampleAsset(overrides?: Partial<AssetProcessingSummary>): AssetProcessingSummary {
  return {
    asset_id: 'asset-1',
    file_name: 'photo-a.jpg',
    thumbnail_url: null,
    status: 'failed',
    requested_mode: 'HYBRID',
    executed_strategy: 'INTERNAL',
    resolved_by: null,
    internal_code: null,
    quantity: null,
    attempt_count: 2,
    last_error_code: 'INSUFFICIENT_EVIDENCE',
    warnings: ['warn-1'],
    duration_ms: 1200,
    persistence_status: 'pending',
    has_fallback: true,
    has_manual_result: false,
    estimated_external_cost: 0.12,
    state_version: 3,
    ...overrides,
  };
}

describe('ProcessingAssetList', () => {
  it('renders status badges with text labels', () => {
    render(
      <ProcessingAssetList
        items={[sampleAsset(), sampleAsset({ asset_id: 'asset-2', file_name: 'photo-b.jpg', status: 'resolved' })]}
        total={2}
        page={1}
        pageSize={25}
        isLoading={false}
        onSelectAsset={vi.fn()}
        onPageChange={vi.fn()}
      />
    );

    expect(screen.getByText('Fallida')).toBeInTheDocument();
    expect(screen.getByText('Resuelta')).toBeInTheDocument();
  });

  it('calls onSelectAsset from row action', () => {
    const onSelectAsset = vi.fn();
    render(
      <ProcessingAssetList
        items={[sampleAsset()]}
        total={1}
        page={1}
        pageSize={25}
        isLoading={false}
        onSelectAsset={onSelectAsset}
        onPageChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getAllByRole('button', { name: /ver detalle/i })[0]!);
    expect(onSelectAsset).toHaveBeenCalledWith('asset-1');
  });
});
