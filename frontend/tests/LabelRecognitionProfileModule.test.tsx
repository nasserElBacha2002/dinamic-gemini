import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppSnackbarProvider } from '../src/components/ui';
import LabelRecognitionProfileModule from '../src/features/clients/components/labelRecognition/LabelRecognitionProfileModule';
import i18n from '../src/i18n';
import en from '../src/i18n/locales/en/translation.json';

const { listMock, createMock, capabilitiesMock, refsMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  createMock: vi.fn(),
  capabilitiesMock: vi.fn(),
  refsMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSupplierExtractionProfiles: listMock,
    useCreateSupplierExtractionProfileVersion: createMock,
    useSupplierReferenceImages: refsMock,
    useActiveSupplierExtractionProfile: () => ({
      data: null,
      isError: true,
      error: { status: 404 },
    }),
    useUploadSupplierReferenceImages: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    }),
    useDeleteSupplierReferenceImage: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    }),
  };
});

vi.mock('../src/features/clients/hooks/useExtractionProfileCapabilities', () => ({
  useExtractionProfileCapabilities: capabilitiesMock,
}));

function renderModule() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AppSnackbarProvider>
        <LabelRecognitionProfileModule clientId="client-1" supplierId="supplier-1" supplierName="Proveedor" />
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('LabelRecognitionProfileModule', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('es');
    listMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    createMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    capabilitiesMock.mockReturnValue({
      profile_aware_validation_enabled: true,
      reference_template_annotations_enabled: false,
    });
    refsMock.mockReturnValue({
      data: { items: [] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it('uses label recognition naming in Spanish and English', () => {
    expect(i18n.t('clients.supplier_page.tab_extraction_profile')).toBe('Reconocimiento de etiquetas');
    expect(en.clients.supplier_page.tab_extraction_profile).toBe('Label recognition');
    expect(i18n.t('clients.extraction_profile.title')).toBe('Reconocimiento de etiquetas');
  });

  it('shows independent item and position tabs with DINAMIC/SUPPLIER source', () => {
    renderModule();
    expect(screen.getByRole('tab', { name: 'Etiquetas de producto' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Etiquetas de posición' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'DINAMIC' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'PROVEEDOR' })).toBeInTheDocument();
  });

  it('offers SIMPLE/SEGMENTED/GS1, validations, visual hints, examples and tester', () => {
    renderModule();
    expect(screen.getByRole('button', { name: 'Código simple' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Código segmentado' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'GS1' })).toBeInTheDocument();
    expect(screen.getByLabelText('Prefijo esperado')).toBeInTheDocument();
    expect(screen.getByLabelText('Sufijo esperado')).toBeInTheDocument();
    expect(screen.getByLabelText('Longitud exacta')).toBeInTheDocument();
    expect(screen.getByLabelText('Caracteres permitidos')).toBeInTheDocument();
    expect(screen.getByText('Quitar espacios exteriores')).toBeInTheDocument();
    expect(screen.getByText('Estas características ayudan a localizar e interpretar la etiqueta en imágenes. Las validaciones del código se configuran arriba.')).toBeInTheDocument();
    expect(screen.getByText('Ejemplos válidos')).toBeInTheDocument();
    expect(screen.getByText('Ejemplos inválidos')).toBeInTheDocument();
    expect(screen.getByText('Esta prueba no modifica inventarios.')).toBeInTheDocument();
    expect(screen.getByText(/Imágenes de referencia — ITEM/)).toBeInTheDocument();
  });

  it('keeps dirty drafts when switching kind after confirm', () => {
    window.confirm = vi.fn(() => true);
    renderModule();
    fireEvent.change(screen.getByLabelText('Prefijo esperado'), { target: { value: 'ABC' } });
    fireEvent.click(screen.getByRole('tab', { name: 'Etiquetas de posición' }));
    expect(window.confirm).toHaveBeenCalled();
    expect(screen.getByRole('tab', { name: 'Etiquetas de posición', selected: true })).toBeInTheDocument();
  });
});
