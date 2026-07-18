/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
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

describe('AisleProcessingDialog identification mode', () => {
  const baseProps = {
    open: true,
    aisleCode: 'A01',
    clientSupplierId: null as string | null,
    providerKey: '',
    onProviderKeyChange: vi.fn(),
    modelKey: '',
    onModelKeyChange: vi.fn(),
    identificationMode: 'LEGACY_LLM',
    onIdentificationModeChange: vi.fn(),
    inheritedEffectiveMode: 'LEGACY_LLM',
    identificationModeSource: 'SYSTEM_DEFAULT',
    providerOptsQuery: {
      data: {
        mode: 'test' as const,
        default_provider_key: 'gemini',
        default_model_key: null,
        default_prompt_key: 'global_v22',
        prompt_profiles: [],
        providers: [],
      },
      isLoading: false,
      isError: false,
      error: null,
    },
    providerConfig: undefined,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    confirmDisabled: false,
    confirmBusyLabel: false,
  };

  it('renders three identification options and source', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-identification-mode')).toBeInTheDocument();
    expect(screen.getByTestId('process-identification-source')).toBeInTheDocument();
    expect(screen.queryByTestId('process-identification-phase1-warning')).not.toBeInTheDocument();
  });

  it('shows phase-1 warning for CODE_SCAN', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} identificationMode="CODE_SCAN" />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-identification-phase1-warning')).toBeInTheDocument();
  });

  it('shows phase-1 warning for INTERNAL_OCR', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} identificationMode="INTERNAL_OCR" />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-identification-phase1-warning')).toBeInTheDocument();
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
