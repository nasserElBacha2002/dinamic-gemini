import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import AdminAiConfigPage from '../src/pages/AdminAiConfigPage';
import { AppSnackbarProvider } from '../src/components/ui';
import { AuthContext, createInitialAuthState } from '../src/features/auth/store';
import type { AuthContextValue } from '../src/features/auth/store';
import * as client from '../src/api/client';

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api/client')>();
  return { ...actual, getAdminAiConfig: vi.fn() };
});

const sampleContract = {
  expects_json: true,
  validation_function: 'validate_global_analysis_structure_v21',
  normalization_function: 'normalize_llm_response',
  normalization_family: 'gemini',
  required_root_keys: ['total_entities_detected', 'entities'],
  extra_root_keys_policy: 'extras ignored',
  required_entity_keys: ['entity_type', 'model_entity_id', 'confidence', 'has_boxes'],
  canonical_entity_keys: ['entity_type', 'model_entity_id'],
  nullable_optional_entity_keys: ['internal_code'],
  canonical_example_json: '{"total_entities_detected":0,"entities":[]}',
  raw_provider_expectation: 'JSON object from model.',
  canonical_contract_summary: 'Canonical v2.1 shape.',
  provider_wire_notes: ['note a'],
  normalization_notes: ['note b'],
};

const sampleComposition = {
  hybrid_base_resolution: 'default branch',
  parity_mode: 'parity text',
  multimodal_context_rules: 'multimodal text',
  provider_composition_summary: 'summary',
  bullets: ['a', 'b'],
};

const samplePayload = {
  generated_at: '2026-01-01T00:00:00+00:00',
  server_defaults: { llm_provider: 'gemini', hybrid_prompt_key: 'global_v21', prompt_version: null },
  providers: [
    {
      key: 'gemini',
      label: 'Gemini',
      description: 'd',
      execution_mode: 'native',
      models: [{ id: 'm1', label: 'm1', is_default: true }],
      default_model: 'm1',
      overview: {
        is_default_pipeline_provider: true,
        credential_configured: true,
        operationally_available: true,
        multimodal_aisle_analysis_supported: true,
        execution_mode: 'native',
      },
      instructions: { provider_specific_note: 'note' },
      response_contract: sampleContract,
      composition_notes: sampleComposition,
      prompt_variants: [
        {
          prompt_key: 'global_v21',
          pipeline_provider_key: 'gemini',
          prompt_parity_mode: false,
          variant_label: 'v1',
          composed_prompt_text: 'x'.repeat(5000),
        },
      ],
    },
  ],
  prompt_catalog: [{ key: 'global_v21', label: 'A', description: 'x' }],
  global_instructions_note: 'Global note text.',
};

function renderWithAuth(user: { username: string } | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const auth: AuthContextValue = {
    ...createInitialAuthState(true),
    user: user
      ? { id: 'admin', username: user.username, role: 'administrator' }
      : null,
    token: user ? 't' : null,
    login: vi.fn(),
    logout: vi.fn(),
  };
  return render(
    <QueryClientProvider client={qc}>
      <AuthContext.Provider value={auth}>
        <AppSnackbarProvider>
          <MemoryRouter>
            <AdminAiConfigPage />
          </MemoryRouter>
        </AppSnackbarProvider>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

describe('AdminAiConfigPage', () => {
  beforeEach(() => {
    vi.mocked(client.getAdminAiConfig).mockReset();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('shows loading then provider explorer and composed prompt after opening Prompts tab', async () => {
    vi.mocked(client.getAdminAiConfig).mockResolvedValue(samplePayload as never);
    renderWithAuth({ username: 'admin' });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/Snapshot generated|Instantánea generada/i)).toBeInTheDocument()
    );
    expect(screen.getAllByText('Gemini').length).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole('tab', { name: /instructions/i }));
    await waitFor(() => expect(screen.getByLabelText('global-instructions')).toBeInTheDocument());
    const pre = screen.getByLabelText('global-instructions');
    expect(pre.textContent).toContain('Global note');
    fireEvent.click(screen.getByRole('tab', { name: /prompts/i }));
    await waitFor(() => expect(document.body.textContent).toContain('x'.repeat(200)));
  });

  it('shows forbidden message when API returns 403', async () => {
    const { ApiError } = await import('../src/api/types');
    vi.mocked(client.getAdminAiConfig).mockRejectedValue(new ApiError('no', 403, {}));
    renderWithAuth({ username: 'admin' });
    await waitFor(() => expect(screen.getByText(/not allowed|forbidden|permiso/i)).toBeInTheDocument());
  });

  it('copy button triggers clipboard write', async () => {
    vi.mocked(client.getAdminAiConfig).mockResolvedValue(samplePayload as never);
    renderWithAuth({ username: 'admin' });
    await waitFor(() => expect(screen.getByRole('tab', { name: /instructions/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: /instructions/i }));
    await waitFor(() => expect(screen.getAllByLabelText(/copy/i).length).toBeGreaterThan(0));
    await act(async () => {
      fireEvent.click(screen.getAllByLabelText(/copy/i)[0]);
    });
    expect(navigator.clipboard.writeText).toHaveBeenCalled();
  });
});
