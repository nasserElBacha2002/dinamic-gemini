import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppSnackbarProvider } from '../src/components/ui';
import SupplierExtractionProfilesModule from '../src/features/clients/components/SupplierExtractionProfilesModule';

const {
  useSupplierExtractionProfilesMock,
  useActiveSupplierExtractionProfileMock,
  useCreateSupplierExtractionProfileVersionMock,
  useActivateSupplierExtractionProfileVersionMock,
  useCloneSupplierExtractionProfileMock,
  useExtractionProfileCapabilitiesMock,
} = vi.hoisted(() => ({
  useSupplierExtractionProfilesMock: vi.fn(),
  useActiveSupplierExtractionProfileMock: vi.fn(),
  useCreateSupplierExtractionProfileVersionMock: vi.fn(),
  useActivateSupplierExtractionProfileVersionMock: vi.fn(),
  useCloneSupplierExtractionProfileMock: vi.fn(),
  useExtractionProfileCapabilitiesMock: vi.fn(),
}));

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSupplierExtractionProfiles: useSupplierExtractionProfilesMock,
    useActiveSupplierExtractionProfile: useActiveSupplierExtractionProfileMock,
    useCreateSupplierExtractionProfileVersion: useCreateSupplierExtractionProfileVersionMock,
    useActivateSupplierExtractionProfileVersion: useActivateSupplierExtractionProfileVersionMock,
    useCloneSupplierExtractionProfile: useCloneSupplierExtractionProfileMock,
  };
});

vi.mock('../src/features/clients/hooks/useExtractionProfileCapabilities', () => ({
  useExtractionProfileCapabilities: useExtractionProfileCapabilitiesMock,
}));

const activeProfile = {
  id: 'profile-1',
  client_id: 'client-1',
  supplier_id: 'supplier-1',
  profile_key: 'default',
  version: 1,
  status: 'ACTIVE',
  configuration: {
    internal_code_sources: [],
    quantity_rules: {
      aliases: [],
      required: false,
      data_type: 'INTEGER',
      minimum: 0,
      maximum: 9999,
      allow_decimals: false,
    },
    additional_fields: [],
    validation_rules: {
      code: {
        min_length: 1,
        max_length: 64,
        allow_letters: true,
        allow_digits: true,
        allow_hyphen: true,
        allow_slash: true,
        allow_spaces: false,
        preserve_leading_zeros: true,
        regex: null,
      },
      ean: {
        allow_ean8: true,
        allow_ean12: true,
        allow_ean13: true,
        allow_ean14: true,
        validate_checksum: true,
      },
      quantity_integer_only: false,
    },
    accepted_barcode_formats: [],
  },
  visual_notes: null,
  created_by: null,
  created_at: '2024-01-01T00:00:00Z',
  activated_by: null,
  activated_at: '2024-01-02T00:00:00Z',
  superseded_at: null,
  updated_at: '2024-01-02T00:00:00Z',
  row_version: 1,
};

function renderModule() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AppSnackbarProvider>
        <SupplierExtractionProfilesModule
          clientId="client-1"
          supplierId="supplier-1"
          supplierName="Proveedor Test"
        />
      </AppSnackbarProvider>
    </QueryClientProvider>
  );
}

describe('SupplierExtractionProfilesModule feature flags', () => {
  beforeEach(() => {
    useSupplierExtractionProfilesMock.mockReturnValue({
      data: { items: [activeProfile] },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useActiveSupplierExtractionProfileMock.mockReturnValue({
      data: activeProfile,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    useCreateSupplierExtractionProfileVersionMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(activeProfile),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useActivateSupplierExtractionProfileVersionMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(activeProfile),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useCloneSupplierExtractionProfileMock.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue(activeProfile),
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    useExtractionProfileCapabilitiesMock.mockReturnValue({
      reference_template_annotations_enabled: false,
      profile_aware_validation_enabled: false,
      client_extraction_profiles_enabled: false,
      source: 'fallback',
      isLoading: false,
    });
  });

  it('shows warning when profile-aware validation is disabled', () => {
    renderModule();
    expect(screen.getByRole('status')).toHaveTextContent(/validación con perfil está deshabilitada/i);
    expect(screen.getByText(/no aplicado en procesamiento/i)).toBeInTheDocument();
  });

  it('still allows save and activate when profile-aware is disabled', async () => {
    const mutateAsync = vi.fn().mockResolvedValue(activeProfile);
    useCreateSupplierExtractionProfileVersionMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      isError: false,
      error: null,
      reset: vi.fn(),
    });
    renderModule();
    fireEvent.click(screen.getByRole('button', { name: /guardar y activar/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  });

  it('marks active version as applied when profile-aware is enabled', () => {
    useExtractionProfileCapabilitiesMock.mockReturnValue({
      reference_template_annotations_enabled: true,
      profile_aware_validation_enabled: true,
      client_extraction_profiles_enabled: true,
      source: 'backend',
      isLoading: false,
    });
    renderModule();
    expect(screen.getByText(/aplicado en procesamiento/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/validación con perfil está deshabilitada/i)
    ).not.toBeInTheDocument();
  });
});
