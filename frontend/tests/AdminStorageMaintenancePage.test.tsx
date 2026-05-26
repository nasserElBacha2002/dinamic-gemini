import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminStorageMaintenancePage from '../src/pages/AdminStorageMaintenancePage';
import { AppSnackbarProvider } from '../src/components/ui';
import { AuthContext, createInitialAuthState } from '../src/features/auth/store';
import type { AuthContextValue } from '../src/features/auth/store';
import * as adminStorageApi from '../src/api/adminStorageApi';

vi.mock('../src/api/adminStorageApi', () => ({
  postAdminStorageCleanup: vi.fn(),
}));

const sampleSummary = {
  ok: true,
  mode: 'dry_run' as const,
  target: 'both' as const,
  remote: {
    provider: 'gcs',
    bucket: 'b',
    prefix: 'v3',
    objects_found: 2,
    objects_deleted: 0,
    objects_skipped_protected: 0,
    objects_skipped_not_allowed: 0,
    bytes_found: 100,
    bytes_deleted: 0,
    skipped: false,
    skip_reason: null,
    errors: [],
    allowed_prefixes: ['uploads/', 'capture/staging/'],
    protected_prefixes: ['client_suppliers/'],
  },
  local: {
    output_dir: 'output',
    safe_roots: ['output/v3_uploads/uploads'],
    allowed_roots: ['uploads/', 'capture/staging/'],
    protected_roots: ['client_suppliers/'],
    files_found: 1,
    files_deleted: 0,
    files_skipped_protected: 0,
    files_skipped_not_allowed: 0,
    bytes_found: 50,
    bytes_deleted: 0,
    skipped: false,
    skip_reason: null,
    errors: [],
  },
};

function adminAuthContext(): AuthContextValue {
  const auth = createInitialAuthState(true);
  auth.user = { id: 'admin', username: 'admin', role: 'administrator' };
  return {
    ...auth,
    login: vi.fn(),
    logout: vi.fn(),
  };
}

function renderPage(auth: AuthContextValue) {
  return render(
    <AuthContext.Provider value={auth}>
      <AppSnackbarProvider>
        <AdminStorageMaintenancePage />
      </AppSnackbarProvider>
    </AuthContext.Provider>
  );
}

describe('AdminStorageMaintenancePage', () => {
  beforeEach(() => {
    vi.mocked(adminStorageApi.postAdminStorageCleanup).mockReset();
  });

  it('renders simulate button for admin user', () => {
    renderPage(adminAuthContext());
    expect(screen.getByRole('button', { name: /simular limpieza de inventario/i })).toBeInTheDocument();
  });

  it('include_jobs checkbox defaults unchecked', () => {
    renderPage(adminAuthContext());
    const checkbox = screen.getByRole('checkbox', {
      name: /incluir artefactos de jobs/i,
    });
    expect(checkbox).not.toBeChecked();
  });

  it('dry-run enables delete after confirmation; toggling include_jobs disables delete', async () => {
    vi.mocked(adminStorageApi.postAdminStorageCleanup).mockResolvedValue(sampleSummary);
    renderPage(adminAuthContext());

    fireEvent.click(screen.getByRole('button', { name: /simular limpieza de inventario/i }));
    await waitFor(() => {
      expect(screen.getByText(/Objetos encontrados/i)).toBeInTheDocument();
    });

    const deleteBtn = screen.getByRole('button', {
      name: /eliminar archivos operativos de inventario/i,
    });
    expect(deleteBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/confirmación/i), {
      target: { value: 'DELETE_INVENTORY_ARTIFACTS' },
    });
    expect(deleteBtn).not.toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox', { name: /incluir artefactos de jobs/i }));
    expect(deleteBtn).toBeDisabled();
  });
});
