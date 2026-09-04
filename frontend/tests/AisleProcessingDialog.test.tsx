/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import AisleProcessingDialog from '../src/features/inventories/components/AisleProcessingDialog';

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

describe('AisleProcessingDialog processing modes', () => {
  const baseProps = {
    open: true,
    aisleCode: 'A01',
    clientSupplierId: null as string | null,
    providerKey: 'gemini',
    onProviderKeyChange: vi.fn(),
    modelKey: 'gemini-x',
    onModelKeyChange: vi.fn(),
    processingMode: 'AUTO' as const,
    onProcessingModeChange: vi.fn(),
    inheritedEffectiveMode: 'CODE_SCAN',
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

  it('offers AUTO, CODE_SCAN_ONLY, VISION_ONLY and not OCR/LEGACY', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} />
      </I18nextProvider>
    );
    fireEvent.mouseDown(within(screen.getByTestId('process-processing-mode')).getByRole('combobox'));
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getByTestId('process-processing-mode-auto')).toBeInTheDocument();
    expect(within(listbox).getByTestId('process-processing-mode-code_scan_only')).toBeInTheDocument();
    expect(within(listbox).getByTestId('process-processing-mode-vision_only')).toBeInTheDocument();
    expect(within(listbox).queryByText(/OCR|Tesseract|INTERNAL_OCR|LEGACY_LLM/i)).not.toBeInTheDocument();
  });

  it('shows AUTO help and external-send warning by default', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-processing-mode-help')).toHaveTextContent(
      /Primero intenta resolver|First tries to resolve/i
    );
    expect(screen.getByTestId('process-vision-external-send')).toBeInTheDocument();
    expect(screen.getByTestId('process-provider-select')).toBeInTheDocument();
  });

  it('shows code-only copy and no AI send for CODE_SCAN_ONLY', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} processingMode="CODE_SCAN_ONLY" />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-processing-mode-help')).toHaveTextContent(
      /únicamente códigos|only QR or barcodes/i
    );
    expect(screen.getByTestId('process-no-immediate-external')).toBeInTheDocument();
    expect(screen.queryByTestId('process-provider-select')).not.toBeInTheDocument();
    expect(screen.queryByTestId('process-vision-external-send')).not.toBeInTheDocument();
  });

  it('shows Vision diagnostic note and provider controls for VISION_ONLY', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} processingMode="VISION_ONLY" />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-vision-diagnostic-note')).toBeInTheDocument();
    expect(screen.getByTestId('process-vision-external-send')).toBeInTheDocument();
    expect(screen.getByTestId('process-provider-select')).toBeInTheDocument();
  });

  it('disables VISION_ONLY when no providers are available', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog
          {...baseProps}
          processingMode="VISION_ONLY"
          providerOptsQuery={{
            ...baseProps.providerOptsQuery,
            data: {
              ...baseProps.providerOptsQuery.data!,
              providers: [],
            },
          }}
          providerConfig={undefined}
        />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-vision-provider-missing')).toBeInTheDocument();
    expect(screen.getByTestId('process-aisle-confirm')).toBeDisabled();
  });

  it('warns when inherited effective identification mode is still legacy', () => {
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
    const btn = screen.getByTestId('process-aisle-confirm');
    fireEvent.click(btn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
