import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProcessingAssetDrawer from '../../../src/features/processing/ProcessingAssetDrawer';
import type { AssetProcessingDetail } from '../../../src/api/types/processing';
import { AppSnackbarProvider } from '../../../src/components/ui';

vi.mock('../../../src/features/processing/ProcessingEvidencePanel', () => ({
  default: () => <div data-testid="processing-evidence-panel">evidence</div>,
}));

vi.mock('../../../src/features/processing/ProcessingActionsPanel', () => ({
  default: () => <div data-testid="processing-actions-panel">actions</div>,
}));

function fullDetail(overrides?: Partial<AssetProcessingDetail>): AssetProcessingDetail {
  return {
    asset: {
      asset_id: 'asset-1',
      file_name: 'photo-a.jpg',
      thumbnail_url: null,
      status: 'resolved',
      requested_mode: 'HYBRID',
      executed_strategy: 'INTERNAL',
      resolved_by: 'internal',
      internal_code: 'SKU-1',
      quantity: 2,
      attempt_count: 1,
      last_error_code: null,
      warnings: [],
      duration_ms: 900,
      persistence_status: 'persisted',
      has_fallback: false,
      has_manual_result: false,
      estimated_external_cost: null,
      state_version: 1,
    },
    current_state: {},
    active_result: { sku: 'SKU-1' },
    position: null,
    attempts: [{ id: 'att-1', status: 'resolved', strategy: 'INTERNAL' }],
    external_requests: [],
    profile_snapshot: null,
    events: [{ id: 'ev-1', event_type: 'attempt_started', timestamp: '2026-01-01T00:00:00Z', message: 'start' }],
    available_actions: {
      can_reprocess: true,
      can_retry_persistence: false,
      can_send_to_external: false,
      can_assign_manual: false,
      can_invalidate: true,
      can_view_sensitive_evidence: false,
    },
    historical_incomplete: false,
    ...overrides,
  };
}

describe('ProcessingAssetDrawer', () => {
  it('renders drawer sections on happy path', () => {
    render(
      <AppSnackbarProvider>
        <ProcessingAssetDrawer
          open
          onClose={vi.fn()}
          inventoryId="inv-1"
          aisleId="aisle-1"
          jobId="job-1"
          detail={fullDetail()}
          isLoading={false}
          error={null}
        />
      </AppSnackbarProvider>
    );

    expect(screen.getByTestId('processing-drawer-summary')).toBeInTheDocument();
    expect(screen.getByTestId('processing-drawer-attempts-section')).toBeInTheDocument();
    expect(screen.getByTestId('processing-drawer-evidence-section')).toBeInTheDocument();
    expect(screen.getByTestId('processing-drawer-logs-section')).toBeInTheDocument();
    expect(screen.getByTestId('processing-actions-panel')).toBeInTheDocument();
  });

  it('shows historical incomplete message', () => {
    render(
      <AppSnackbarProvider>
        <ProcessingAssetDrawer
          open
          onClose={vi.fn()}
          inventoryId="inv-1"
          aisleId="aisle-1"
          jobId="job-1"
          detail={fullDetail({ historical_incomplete: true, attempts: [] })}
          isLoading={false}
          error={null}
        />
      </AppSnackbarProvider>
    );

    expect(screen.getByTestId('processing-drawer-historical')).toHaveTextContent(
      /información no disponible/i
    );
  });
});
