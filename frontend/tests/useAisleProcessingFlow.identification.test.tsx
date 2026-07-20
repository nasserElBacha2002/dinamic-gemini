/**
 * @vitest-environment jsdom
 *
 * requestedIdentificationModeOverride: null omits `identificationMode` from the mutation call
 * (inherited hierarchy applies); a non-null override is sent as-is for that run only.
 */
import { useEffect } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import { AppSnackbarProvider } from '../src/components/ui';
import AisleProcessingDialog from '../src/features/inventories/components/AisleProcessingDialog';
import {
  INHERITED_IDENTIFICATION_MODE,
  useAisleProcessingFlow,
} from '../src/features/inventories/hooks/useAisleProcessingFlow';

const mutateAsyncMock = vi.fn().mockResolvedValue({ job_id: 'job-1' });

const providerOptionsData = {
  mode: 'test' as const,
  default_provider_key: 'gemini',
  default_model_key: null,
  default_prompt_key: 'global_v22',
  prompt_profiles: [],
  providers: [
    {
      key: 'gemini',
      label: 'Gemini',
      default_model: 'gemini-2.5',
      models: [{ id: 'gemini-2.5', label: 'Gemini 2.5' }],
    },
  ],
};

vi.mock('../src/hooks', () => ({
  useProcessingProviderOptions: () => ({
    data: providerOptionsData,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useStartAisleProcessing: () => ({
    mutateAsync: mutateAsyncMock,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <AppSnackbarProvider>{children}</AppSnackbarProvider>
    </I18nextProvider>
  );
}

type Identification = {
  effectiveMode?: string | null;
  source?: string | null;
  configured?: string | null;
};

/** Mirrors the real wiring in `pages/InventoryDetail.tsx` between the flow hook and the dialog. */
function ProcessingHarness({ identification }: { identification?: Identification }) {
  const processFlow = useAisleProcessingFlow({ inventoryId: 'inv-1', isProductionInventory: false });
  useEffect(() => {
    void processFlow.requestProcess('aisle-1', 'A01', null, identification);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <AisleProcessingDialog
      open={Boolean(processFlow.dialogTarget)}
      aisleCode={processFlow.dialogTarget?.aisleCode ?? null}
      clientSupplierId={processFlow.dialogTarget?.clientSupplierId ?? null}
      providerKey={processFlow.providerKey}
      onProviderKeyChange={processFlow.setProviderKey}
      modelKey={processFlow.modelKey}
      onModelKeyChange={processFlow.setModelKey}
      identificationMode={processFlow.identificationMode}
      onIdentificationModeChange={processFlow.setIdentificationMode}
      inheritedEffectiveMode={processFlow.dialogTarget?.effectiveIdentificationMode}
      identificationModeSource={processFlow.dialogTarget?.identificationModeSource}
      providerOptsQuery={processFlow.providerOptsQuery}
      providerConfig={processFlow.providerConfig}
      onClose={processFlow.closeDialog}
      onConfirm={() => void processFlow.confirmDialog()}
      confirmDisabled={false}
      confirmBusyLabel={false}
    />
  );
}

describe('useAisleProcessingFlow — identification mode override wiring', () => {
  beforeEach(() => {
    mutateAsyncMock.mockClear();
  });

  it('walks CLIENT-inherited CODE_SCAN through override → back to inherited', async () => {
    const { result } = renderHook(
      () => useAisleProcessingFlow({ inventoryId: 'inv-1', isProductionInventory: false }),
      { wrapper }
    );

    // Open with CLIENT inheritance resolving to CODE_SCAN; default selection stays inherited.
    act(() => {
      void result.current.requestProcess('aisle-1', 'A01', null, {
        effectiveMode: 'CODE_SCAN',
        source: 'CLIENT',
        configured: null,
      });
    });
    expect(result.current.identificationMode).toBe(INHERITED_IDENTIFICATION_MODE);
    expect(result.current.requestedIdentificationModeOverride).toBeNull();

    // Confirm without changing anything — no identificationMode key in the mutation call.
    await act(async () => {
      await result.current.confirmDialog();
    });
    expect(mutateAsyncMock).toHaveBeenCalledTimes(1);
    let call = mutateAsyncMock.mock.calls[0][0] as Record<string, unknown>;
    expect(call.aisleId).toBe('aisle-1');
    expect(call).not.toHaveProperty('identificationMode');

    // Reopen and override to CODE_SCAN explicitly — sent this time.
    act(() => {
      void result.current.requestProcess('aisle-1', 'A01', null, {
        effectiveMode: 'CODE_SCAN',
        source: 'CLIENT',
        configured: null,
      });
    });
    act(() => {
      result.current.setIdentificationMode('CODE_SCAN');
    });
    expect(result.current.identificationMode).toBe('CODE_SCAN');
    await act(async () => {
      await result.current.confirmDialog();
    });
    expect(mutateAsyncMock).toHaveBeenCalledTimes(2);
    call = mutateAsyncMock.mock.calls[1][0] as Record<string, unknown>;
    expect(call.identificationMode).toBe('CODE_SCAN');

    // Reopen and override to INTERNAL_OCR.
    act(() => {
      void result.current.requestProcess('aisle-1', 'A01', null, {
        effectiveMode: 'CODE_SCAN',
        source: 'CLIENT',
        configured: null,
      });
    });
    act(() => {
      result.current.setIdentificationMode('INTERNAL_OCR');
    });
    await act(async () => {
      await result.current.confirmDialog();
    });
    expect(mutateAsyncMock).toHaveBeenCalledTimes(3);
    call = mutateAsyncMock.mock.calls[2][0] as Record<string, unknown>;
    expect(call.identificationMode).toBe('INTERNAL_OCR');

    // Reopen and override to LEGACY_LLM.
    act(() => {
      void result.current.requestProcess('aisle-1', 'A01', null, {
        effectiveMode: 'CODE_SCAN',
        source: 'CLIENT',
        configured: null,
      });
    });
    act(() => {
      result.current.setIdentificationMode('LEGACY_LLM');
    });
    await act(async () => {
      await result.current.confirmDialog();
    });
    expect(mutateAsyncMock).toHaveBeenCalledTimes(4);
    call = mutateAsyncMock.mock.calls[3][0] as Record<string, unknown>;
    expect(call.identificationMode).toBe('LEGACY_LLM');

    // Reopen, pick an override, then switch back to inherited before confirming — omitted again.
    act(() => {
      void result.current.requestProcess('aisle-1', 'A01', null, {
        effectiveMode: 'CODE_SCAN',
        source: 'CLIENT',
        configured: null,
      });
    });
    act(() => {
      result.current.setIdentificationMode('CODE_SCAN');
    });
    act(() => {
      result.current.setIdentificationMode(INHERITED_IDENTIFICATION_MODE);
    });
    expect(result.current.identificationMode).toBe(INHERITED_IDENTIFICATION_MODE);
    expect(result.current.requestedIdentificationModeOverride).toBeNull();
    await act(async () => {
      await result.current.confirmDialog();
    });
    expect(mutateAsyncMock).toHaveBeenCalledTimes(5);
    call = mutateAsyncMock.mock.calls[4][0] as Record<string, unknown>;
    expect(call).not.toHaveProperty('identificationMode');
  });

  it.each([
    ['INVENTORY', 'Inventario'],
    ['AISLE', 'Pasillo'],
    ['SYSTEM_DEFAULT', 'Configuración general'],
  ] as const)(
    'renders the inherited source label for %s through the dialog',
    async (source, expectedLabelFragment) => {
      render(<ProcessingHarness identification={{ effectiveMode: 'LEGACY_LLM', source }} />, {
        wrapper,
      });

      const sourceNode = await screen.findByTestId('process-identification-source');
      expect(sourceNode).toHaveTextContent(expectedLabelFragment);

      // The Select's inherited option also carries the resolved source label.
      fireEvent.mouseDown(
        within(screen.getByTestId('process-identification-mode')).getByRole('combobox')
      );
      expect(screen.getByTestId('process-identification-inherited-option')).toHaveTextContent(
        expectedLabelFragment
      );
    }
  );
});
