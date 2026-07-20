/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import AisleProcessingDialog from '../src/features/inventories/components/AisleProcessingDialog';
import { INHERITED_IDENTIFICATION_MODE } from '../src/features/inventories/hooks/useAisleProcessingFlow';

vi.mock('../src/components/ui/BaseDialog', () => ({
  default: ({
    open,
    title,
    children,
    actions,
  }: {
    open: boolean;
    title: React.ReactNode;
    children: React.ReactNode;
    actions: React.ReactNode;
  }) =>
    open ? (
      <div data-testid="base-dialog">
        <div>{title}</div>
        <div>{children}</div>
        <div>{actions}</div>
      </div>
    ) : null,
}));

describe('AisleProcessingDialog identification mode (Phase 8)', () => {
  const baseProps = {
    open: true,
    aisleCode: 'A01',
    clientSupplierId: null as string | null,
    providerKey: '',
    onProviderKeyChange: vi.fn(),
    modelKey: '',
    onModelKeyChange: vi.fn(),
    identificationMode: INHERITED_IDENTIFICATION_MODE,
    onIdentificationModeChange: vi.fn(),
    inheritedEffectiveMode: 'INTERNAL_OCR',
    identificationModeSource: 'CLIENT',
    providerOptsQuery: {
      data: {
        mode: 'test' as const,
        default_provider_key: 'gemini',
        default_model_key: null,
        default_prompt_key: 'global_v22',
        prompt_profiles: [],
        providers: [
          {
            key: 'gemini',
            label: 'Gemini',
            execution_mode: 'cloud',
            default_model: 'gemini-x',
            models: [{ id: 'gemini-x', label: 'gemini-x' }],
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
    },
    providerConfig: {
      key: 'gemini',
      label: 'Gemini',
      execution_mode: 'cloud',
      default_model: 'gemini-x',
      models: [{ id: 'gemini-x', label: 'gemini-x' }],
    },
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    confirmDisabled: false,
    confirmBusyLabel: false,
  };

  it('does not offer LEGACY_LLM in the selector', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} />
      </I18nextProvider>
    );
    fireEvent.mouseDown(within(screen.getByTestId('process-identification-mode')).getByRole('combobox'));
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).queryByText(/Procesamiento tradicional|Traditional processing|LEGACY_LLM/i)).not.toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: /Escanear QR|Scan QR/i })).toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: /^Leer etiqueta|^Read label/i })).toBeInTheDocument();
    expect(within(listbox).queryByRole('option', { name: /LEGACY_LLM|tradicional|Traditional processing/i })).not.toBeInTheDocument();
  });

  it('defaults to the default-config sentinel with business wording', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} />
      </I18nextProvider>
    );
    fireEvent.mouseDown(within(screen.getByTestId('process-identification-mode')).getByRole('combobox'));
    const inheritedOption = screen.getByTestId('process-identification-inherited-option');
    expect(inheritedOption).toHaveTextContent(
      i18n.t('aisle.identification_use_default', {
        mode: i18n.t('aisle.identification_mode_internal_ocr'),
        source: i18n.t('aisle.identification_source_client'),
      })
    );
  });

  it('hides AI provider controls for INTERNAL_OCR', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} identificationMode="INTERNAL_OCR" />
      </I18nextProvider>
    );
    expect(screen.queryByTestId('process-provider-select')).not.toBeInTheDocument();
    expect(screen.getByTestId('process-no-immediate-external')).toBeInTheDocument();
    expect(screen.getByTestId('process-identification-mode-help')).toBeInTheDocument();
  });

  it('hides AI provider controls for CODE_SCAN', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} identificationMode="CODE_SCAN" />
      </I18nextProvider>
    );
    expect(screen.queryByTestId('process-provider-select')).not.toBeInTheDocument();
    expect(screen.getByTestId('process-no-immediate-external')).toBeInTheDocument();
  });

  it('warns when inherited effective mode is still legacy', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} inheritedEffectiveMode="LEGACY_LLM" />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-legacy-retirement-warning')).toBeInTheDocument();
  });

  it('does not fire confirm twice from a single click', () => {
    const onConfirm = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} onConfirm={onConfirm} />
      </I18nextProvider>
    );
    const btn = screen.getByRole('button', { name: /Procesar|Process start/i });
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
