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

describe('AisleProcessingDialog identification mode', () => {
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

  it('defaults to the inherited sentinel and renders the inherited option', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} />
      </I18nextProvider>
    );
    expect(baseProps.identificationMode).toBe(INHERITED_IDENTIFICATION_MODE);
    fireEvent.mouseDown(within(screen.getByTestId('process-identification-mode')).getByRole('combobox'));
    const inheritedOption = screen.getByTestId('process-identification-inherited-option');
    expect(inheritedOption).toBeInTheDocument();
    expect(inheritedOption).toHaveTextContent(
      i18n.t('aisle.identification_use_inherited', {
        mode: baseProps.inheritedEffectiveMode,
        source: i18n.t(
          `aisle.identification_source_${baseProps.identificationModeSource.toLowerCase()}`
        ),
      })
    );
  });

  it('shows the inherited reference (not the request-scoped label) when using inherited', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} />
      </I18nextProvider>
    );
    const sourceNode = screen.getByTestId('process-identification-source');
    expect(sourceNode).toHaveTextContent(
      i18n.t('aisle.identification_inherited_reference', {
        mode: baseProps.inheritedEffectiveMode,
        source: i18n.t(
          `aisle.identification_source_${baseProps.identificationModeSource.toLowerCase()}`
        ),
      })
    );
    expect(sourceNode).not.toHaveTextContent(i18n.t('aisle.identification_source_request_label'));
  });

  it('shows the request-scoped source label when an explicit override is selected', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} identificationMode="CODE_SCAN" />
      </I18nextProvider>
    );
    expect(screen.getByTestId('process-identification-source')).toHaveTextContent(
      i18n.t('aisle.identification_source_request_label')
    );
  });

  it('does not show phase-1 warning for CODE_SCAN (native path)', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <AisleProcessingDialog {...baseProps} identificationMode="CODE_SCAN" />
      </I18nextProvider>
    );
    expect(screen.queryByTestId('process-identification-phase1-warning')).not.toBeInTheDocument();
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
