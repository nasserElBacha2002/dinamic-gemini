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
    bytes_found: 100,
    bytes_deleted: 0,
    skipped: false,
    skip_reason: null,
    errors: [],
  },
  local: {
    output_dir: 'output',
    safe_roots: ['output/v3_uploads'],
    files_found: 1,
    files_deleted: 0,
    bytes_found: 50,
    bytes_deleted: 0,
    skipped: false,
    skip_reason: null,
    errors: [],
  },
};

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
    const auth = createInitialAuthState();
    auth.user = { id: 'admin', username: 'admin', role: 'administrator' };
    auth.initialized = true;
    renderPage(auth);
    expect(screen.getByRole('button', { name: /simular limpieza/i })).toBeInTheDocument();
  });

  it('dry-run shows summary and enables delete after confirmation', async () => {
    vi.mocked(adminStorageApi.postAdminStorageCleanup).mockResolvedValue(sampleSummary);
    const auth = createInitialAuthState();
    auth.user = { id: 'admin', username: 'admin', role: 'administrator' };
    auth.initialized = true;
    renderPage(auth);

    fireEvent.click(screen.getByRole('button', { name: /simular limpieza/i }));
    await waitFor(() => {
      expect(screen.getByText(/Objetos encontrados/i)).toBeInTheDocument();
    });

    const deleteBtn = screen.getByRole('button', {
      name: /eliminar archivos del bucket y output/i,
    });
    expect(deleteBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/confirmación/i), {
      target: { value: 'DELETE_ARTIFACTS' },
    });
    expect(deleteBtn).not.toBeDisabled();
  });
});
