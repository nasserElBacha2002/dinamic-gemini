import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SupplierReferenceAnnotationEditorDialog from '../src/features/clients/components/SupplierReferenceAnnotationEditorDialog';

const {
  useSupplierReferenceAnnotationsMock,
  useReplaceSupplierReferenceAnnotationsMock,
  fetchSupplierReferenceImageDisplayMock,
} = vi.hoisted(() => ({
  useSupplierReferenceAnnotationsMock: vi.fn(),
  useReplaceSupplierReferenceAnnotationsMock: vi.fn(),
  fetchSupplierReferenceImageDisplayMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSupplierReferenceAnnotations: useSupplierReferenceAnnotationsMock,
    useReplaceSupplierReferenceAnnotations: useReplaceSupplierReferenceAnnotationsMock,
  };
});

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return {
    ...actual,
    fetchSupplierReferenceImageDisplay: fetchSupplierReferenceImageDisplayMock,
  };
});

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SupplierReferenceAnnotationEditorDialog
        open
        onClose={vi.fn()}
        clientId="client-1"
        supplierId="supplier-1"
        imageId="img-1"
        imageLabel="ref-front.jpg"
        activeProfileId="profile-1"
      />
    </QueryClientProvider>
  );
}

describe('SupplierReferenceAnnotationEditorDialog', () => {
  beforeEach(() => {
    fetchSupplierReferenceImageDisplayMock.mockResolvedValue({
      ok: true,
      imageSrc: 'blob:preview',
      revoke: vi.fn(),
    });
    useSupplierReferenceAnnotationsMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'ann-1',
            template_image_id: 'img-1',
            profile_id: 'profile-1',
            field_key: 'internal_code',
            anchor_texts: ['COD'],
            spatial_relation: 'RIGHT_OF',
            normalized_polygon: [
              [0.1, 0.1],
              [0.4, 0.1],
              [0.4, 0.3],
              [0.1, 0.3],
            ],
            priority: 1,
            required: false,
            max_distance_ratio: null,
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useReplaceSupplierReferenceAnnotationsMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ items: [] }),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
  });

  it('renders visual canvas with field labels and keeps JSON under advanced accordion', async () => {
    renderDialog();
    await waitFor(() => {
      expect(screen.getByText(/internal_code · COD/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/seleccionar y mover puntos/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/polígono normalizado \(json\)/i)).not.toBeVisible();
    fireEvent.click(screen.getByText(/avanzado: polígono normalizado \(json\)/i));
    expect(screen.getByLabelText(/polígono normalizado \(json\)/i)).toBeVisible();
  });

  it('persists annotations on save', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ items: [] });
    useReplaceSupplierReferenceAnnotationsMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    renderDialog();
    await waitFor(() => expect(screen.getByRole('button', { name: /^guardar$/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /^guardar$/i }));
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        profile_id: 'profile-1',
        annotations: [
          expect.objectContaining({
            field_key: 'internal_code',
            anchor_texts: ['COD'],
            normalized_polygon: [
              [0.1, 0.1],
              [0.4, 0.1],
              [0.4, 0.3],
              [0.1, 0.3],
            ],
          }),
        ],
      })
    );
  });
});
