import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ReprocessDialog from '../../../src/features/processing/ReprocessDialog';
import * as hooks from '../../../src/features/processing/hooks/useReprocessAsset';
import { AppSnackbarProvider } from '../../../src/components/ui';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AppSnackbarProvider>{ui}</AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('ReprocessDialog', () => {
  it('requires reason before confirming reprocess', async () => {
    const mutateAsync = vi.fn();
    vi.spyOn(hooks, 'useReprocessAsset').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as never);

    wrap(
      <ReprocessDialog
        open
        onClose={vi.fn()}
        inventoryId="inv-1"
        aisleId="aisle-1"
        jobId="job-1"
        asset={{
          asset_id: 'asset-1',
          file_name: 'photo-a.jpg',
          thumbnail_url: null,
          status: 'failed',
          requested_mode: null,
          executed_strategy: 'INTERNAL',
          resolved_by: null,
          internal_code: null,
          quantity: null,
          attempt_count: 1,
          last_error_code: null,
          warnings: [],
          duration_ms: null,
          persistence_status: null,
          has_fallback: false,
          has_manual_result: false,
          estimated_external_cost: 0.5,
          state_version: 2,
        }}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /reprocesar/i }));
    expect(await screen.findByText(/ingresá un motivo/i)).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId('reprocess-reason-input'), {
      target: { value: 'Operador solicitó reproceso' },
    });
    fireEvent.click(screen.getByRole('button', { name: /reprocesar/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          reason: 'Operador solicitó reproceso',
          expected_state_version: 2,
          strategy: 'INTERNAL',
          idempotencyKey: expect.any(String),
        })
      );
    });
  });
});
