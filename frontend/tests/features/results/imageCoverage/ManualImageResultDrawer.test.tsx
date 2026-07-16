/**
 * Manual image coverage drawer — validation, success, and 409 conflict handling.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import ManualImageResultDrawer from '../../../../src/features/results/components/imageCoverage/ManualImageResultDrawer';
import { ApiError } from '../../../../src/api/types';
import type { JobImageResultItem } from '../../../../src/api/types';

const mutateAsyncMock = vi.hoisted(() => vi.fn());
const showSnackbarMock = vi.hoisted(() => vi.fn());
const isPendingRef = vi.hoisted(() => ({ value: false }));

vi.mock('../../../../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../src/hooks')>();
  return {
    ...actual,
    useCreateManualImageResult: () => ({
      mutateAsync: mutateAsyncMock,
      isPending: isPendingRef.value,
    }),
  };
});

vi.mock('../../../../src/components/ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../src/components/ui')>();
  return {
    ...actual,
    useAppSnackbar: () => ({
      showSnackbar: showSnackbarMock,
      closeSnackbar: vi.fn(),
    }),
  };
});

const baseItem: JobImageResultItem = {
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
};

function renderDrawer(overrides?: {
  onClose?: () => void;
  onSuccess?: (position: unknown) => void;
  onConflict?: () => void;
  item?: JobImageResultItem | null;
  open?: boolean;
}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ManualImageResultDrawer
        open={overrides?.open ?? true}
        item={overrides?.item ?? baseItem}
        inventoryId="inv-1"
        aisleId="aisle-1"
        jobId="job-1"
        onClose={overrides?.onClose ?? vi.fn()}
        onSuccess={overrides?.onSuccess}
        onConflict={overrides?.onConflict}
      />
    </QueryClientProvider>
  );
}

describe('ManualImageResultDrawer', () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset();
    showSnackbarMock.mockClear();
    isPendingRef.value = false;
  });

  it('shows validation errors and does not submit when SKU and quantity are empty', async () => {
    renderDrawer();
    fireEvent.click(screen.getByTestId('manual-image-result-save'));

    expect(await screen.findByText(/sku.*obligatorio|sku is required/i)).toBeInTheDocument();
    expect(screen.getByText(/cantidad.*obligatoria|quantity is required/i)).toBeInTheDocument();
    expect(mutateAsyncMock).not.toHaveBeenCalled();
  });

  it('rejects a non-integer / negative quantity', async () => {
    renderDrawer();
    fireEvent.change(screen.getByTestId('manual-image-result-sku'), {
      target: { value: 'SKU-1' },
    });
    fireEvent.change(screen.getByTestId('manual-image-result-quantity'), {
      target: { value: '-3' },
    });
    fireEvent.click(screen.getByTestId('manual-image-result-save'));

    expect(
      await screen.findByText(/cantidad.*entero|quantity must be a whole number/i)
    ).toBeInTheDocument();
    expect(mutateAsyncMock).not.toHaveBeenCalled();
  });

  it('submits with trimmed values and calls onSuccess on success', async () => {
    mutateAsyncMock.mockResolvedValueOnce({
      position: { id: 'pos-new', sku: 'SKU-1' },
    });
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    renderDrawer({ onSuccess, onClose });

    fireEvent.change(screen.getByTestId('manual-image-result-sku'), {
      target: { value: '  SKU-1  ' },
    });
    fireEvent.change(screen.getByTestId('manual-image-result-quantity'), {
      target: { value: '5' },
    });
    fireEvent.click(screen.getByTestId('manual-image-result-save'));

    await waitFor(() => expect(mutateAsyncMock).toHaveBeenCalledTimes(1));
    expect(mutateAsyncMock).toHaveBeenCalledWith({
      job_id: 'job-1',
      sku: 'SKU-1',
      quantity: 5,
      description: undefined,
      position_code: undefined,
    });
    await waitFor(() => expect(showSnackbarMock).toHaveBeenCalledWith(expect.any(String), 'success'));
    expect(onSuccess).toHaveBeenCalledWith({ id: 'pos-new', sku: 'SKU-1' });
    expect(onClose).toHaveBeenCalled();
  });

  it('shows inline error and triggers onConflict on 409 MANUAL_RESULT_ALREADY_EXISTS', async () => {
    mutateAsyncMock.mockRejectedValueOnce(
      new ApiError('conflict', 409, { code: 'MANUAL_RESULT_ALREADY_EXISTS' })
    );
    const onConflict = vi.fn();
    const onClose = vi.fn();
    renderDrawer({ onConflict, onClose });

    fireEvent.change(screen.getByTestId('manual-image-result-sku'), {
      target: { value: 'SKU-2' },
    });
    fireEvent.change(screen.getByTestId('manual-image-result-quantity'), {
      target: { value: '1' },
    });
    fireEvent.click(screen.getByTestId('manual-image-result-save'));

    expect(
      await screen.findByText(/ya tiene un resultado manual|already has a manual result/i)
    ).toBeInTheDocument();
    expect(onConflict).toHaveBeenCalledTimes(1);
    // Drawer stays open on conflict so the operator can see the inline error.
    expect(onClose).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(showSnackbarMock).toHaveBeenCalledWith(expect.any(String), 'error')
    );
  });

  it('does not submit twice on rapid double-click', async () => {
    let resolveMutate: (() => void) | undefined;
    const pending = new Promise((resolve) => {
      resolveMutate = () => resolve({ position: { id: 'pos-new' } });
    });
    mutateAsyncMock.mockImplementationOnce(() => pending);
    renderDrawer();

    fireEvent.change(screen.getByTestId('manual-image-result-sku'), {
      target: { value: 'SKU-1' },
    });
    fireEvent.change(screen.getByTestId('manual-image-result-quantity'), {
      target: { value: '1' },
    });
    const saveBtn = screen.getByTestId('manual-image-result-save');
    fireEvent.click(saveBtn);
    fireEvent.click(saveBtn);

    expect(mutateAsyncMock).toHaveBeenCalledTimes(1);
    resolveMutate?.();
  });
});
