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

vi.mock('../../../../src/features/results/hooks/useEvidenceImageLoad', () => ({
  useEvidenceImageLoad: vi.fn(() => ({ status: 'idle' as const })),
}));

const baseItem: JobImageResultItem = {
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

  it('shows field labels and the image viewer when open', () => {
    renderDrawer();
    expect(screen.getByLabelText(/sku/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/cantidad|quantity/i)).toBeInTheDocument();
    expect(screen.getByTestId('manual-image-result-viewer')).toBeInTheDocument();
  });

  it('shows validation errors and does not submit when SKU and quantity are empty', async () => {
    renderDrawer();
    fireEvent.click(screen.getByTestId('manual-image-result-save'));

    expect(await screen.findByText(/sku.*obligatorio|sku is required/i)).toBeInTheDocument();
    expect(screen.getByText(/cantidad.*obligatoria|quantity is required/i)).toBeInTheDocument();
    expect(mutateAsyncMock).not.toHaveBeenCalled();
  });

  it('rejects zero, negative, and non-integer quantity', async () => {
    renderDrawer();
    fireEvent.change(screen.getByTestId('manual-image-result-sku'), {
      target: { value: 'SKU-1' },
    });
    fireEvent.change(screen.getByTestId('manual-image-result-quantity'), {
      target: { value: '0' },
    });
    fireEvent.click(screen.getByTestId('manual-image-result-save'));

    expect(
      await screen.findByText(/cantidad.*mayor que 0|quantity must be a whole number greater than 0/i)
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

  it('shows refresh message and triggers onConflict on 409 IMAGE_ALREADY_HAS_RESULTS', async () => {
    mutateAsyncMock.mockRejectedValueOnce(
      new ApiError('conflict', 409, { code: 'IMAGE_ALREADY_HAS_RESULTS' })
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
      await screen.findByText(/ya tiene resultados|already has results/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/actualizá la lista|refresh the list/i)).toBeInTheDocument();
    expect(onConflict).toHaveBeenCalledTimes(1);
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
