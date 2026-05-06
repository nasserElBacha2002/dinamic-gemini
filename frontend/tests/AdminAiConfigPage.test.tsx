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
  return {
    ...actual,
    getAdminAiConfig: vi.fn(),
    getAdminAiComposedPrompt: vi.fn(),
  };
});

const sampleResponseContract = {
  expects_json: true,
  wire_transport: 'gemini_native_json',
  validation_function: 'validate_global_analysis_structure_v21',
  normalization_function: 'normalize_llm_response',
  normalization_family: 'gemini',
  alias_promotion_policy: 'legacy_qty_bbox_when_canonical_absent_gemini_family',
  claude_product_label_to_internal_code_when_valid: false,
  required_root_keys: ['total_entities_detected', 'entities'],
  extra_root_keys_policy_short: 'extras ignored',
  required_entity_keys: ['entity_type', 'model_entity_id', 'confidence', 'has_boxes'],
  canonical_entity_keys: ['entity_type', 'model_entity_id'],
  nullable_optional_entity_keys: ['internal_code'],
  canonical_example_json: '{"total_entities_detected":0,"entities":[]}',
  transport_notes: ['note a'],
};

const sampleComposition = {
  hybrid_base_mode: 'default_profile_only',
  parity_mode_affects_prompt_assembly: false,
  multimodal_context_policy: 'attach_when_adapter_supports_vision',
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
      capabilities: {
        is_default_pipeline_provider: true,
        credential_configured: true,
        multimodal_aisle_analysis_supported: true,
        execution_mode: 'native',
      },
      instructions: { provider_specific_note: 'note' },
      response_contract: sampleResponseContract,
      composition: sampleComposition,
      prompt_variant_summaries: [
        {
          prompt_key: 'global_v21',
          pipeline_provider_key: 'gemini',
          prompt_parity_mode: false,
          variant_label: 'global_v21 · gemini · parity=false',
        },
      ],
    },
    {
      key: 'openai',
      label: 'OpenAI',
      description: null,
      execution_mode: 'native',
      models: [],
      default_model: null,
      capabilities: {
        is_default_pipeline_provider: false,
        credential_configured: false,
        multimodal_aisle_analysis_supported: true,
        execution_mode: 'native',
      },
      instructions: { provider_specific_note: '' },
      response_contract: sampleResponseContract,
      composition: sampleComposition,
      prompt_variant_summaries: [],
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
    vi.mocked(client.getAdminAiComposedPrompt).mockReset();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it('shows loading then snapshot and loads composed prompt into the preview region', async () => {
    vi.mocked(client.getAdminAiConfig).mockResolvedValue(samplePayload as never);
    vi.mocked(client.getAdminAiComposedPrompt).mockResolvedValue({
      prompt_key: 'global_v21',
      pipeline_provider_key: 'gemini',
      prompt_parity_mode: false,
      variant_label: 'global_v21 · gemini · parity=false',
      composed_prompt_text: 'x'.repeat(500),
    } as never);

    renderWithAuth({ username: 'admin' });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Generated at raw/i)).toBeInTheDocument());
    expect(screen.getAllByText('Gemini').length).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getByRole('tab', { name: /prompts/i }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /load composed prompt|Cargar prompt/i })).toBeInTheDocument()
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /load composed prompt|Cargar prompt/i }));
    });
    await waitFor(() => expect(screen.getByTestId('composed-prompt-body')).toBeInTheDocument());
    expect(screen.getByTestId('composed-prompt-body').textContent).toContain('x'.repeat(80));
  });

  it('shows global instructions on Instructions tab', async () => {
    vi.mocked(client.getAdminAiConfig).mockResolvedValue(samplePayload as never);
    renderWithAuth({ username: 'admin' });
    await waitFor(() => expect(screen.getByRole('tab', { name: /instructions/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: /instructions/i }));
    await waitFor(() => expect(screen.getByLabelText('global-instructions')).toBeInTheDocument());
    expect(screen.getByLabelText('global-instructions').textContent).toContain('Global note');
  });

  it('shows forbidden message when API returns 403', async () => {
    const { ApiError } = await import('../src/api/types');
    vi.mocked(client.getAdminAiConfig).mockRejectedValue(new ApiError('no', 403, {}));
    renderWithAuth({ username: 'admin' });
    await waitFor(() => expect(screen.getByText(/not allowed|forbidden|permiso/i)).toBeInTheDocument());
  });

  it('copy button triggers clipboard write on instructions tab', async () => {
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

  it('resets to overview when switching provider after viewing prompts', async () => {
    vi.mocked(client.getAdminAiConfig).mockResolvedValue(samplePayload as never);
    renderWithAuth({ username: 'admin' });
    await waitFor(() => expect(screen.getByText('OpenAI')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: /prompts/i }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /load composed prompt|Cargar prompt/i })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByText('OpenAI'));
    await waitFor(() => expect(screen.getByRole('tab', { name: /overview|resumen/i })).toHaveAttribute('aria-selected', 'true'));
  });

  it('shows empty variants when provider has no summaries for the profile', async () => {
    vi.mocked(client.getAdminAiConfig).mockResolvedValue(samplePayload as never);
    renderWithAuth({ username: 'admin' });
    await waitFor(() => expect(screen.getByText('OpenAI')).toBeInTheDocument());
    fireEvent.click(screen.getByText('OpenAI'));
    fireEvent.click(screen.getByRole('tab', { name: /prompts/i }));
    await waitFor(() =>
      expect(screen.getByText(/Empty variants/i)).toBeInTheDocument()
    );
  });
});
