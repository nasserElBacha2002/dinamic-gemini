/**
 * @vitest-environment jsdom
 *
 * processingMode is always sent on confirm (default AUTO).
 */
import { useEffect } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import { AppSnackbarProvider } from '../src/components/ui';
import AisleProcessingDialog from '../src/features/inventories/components/AisleProcessingDialog';
import { useAisleProcessingFlow } from '../src/features/inventories/hooks/useAisleProcessingFlow';

const mutateAsyncMock = vi.fn().mockResolvedValue({ job_id: 'job-1' });

vi.mock('../src/api/aislesApi', () => ({
  getAisleProcessingState: vi.fn().mockResolvedValue({
    state: 'IDLE',
    can_start_new: true,
  }),
  recoverAisleProcessing: vi.fn(),
}));

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
      processingMode={processFlow.processingMode}
      onProcessingModeChange={processFlow.setProcessingMode}
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

describe('useAisleProcessingFlow processing_mode', () => {
  beforeEach(() => {
    mutateAsyncMock.mockClear();
  });

  it('defaults to AUTO and sends processingMode on confirm', async () => {
    const { result } = renderHook(
      () => useAisleProcessingFlow({ inventoryId: 'inv-1', isProductionInventory: false }),
      { wrapper }
    );
    await act(async () => {
      result.current.requestProcess('aisle-1', 'A01', null, {
        effectiveMode: 'CODE_SCAN',
        source: 'CLIENT',
      });
    });
    expect(result.current.processingMode).toBe('AUTO');
    await act(async () => {
      await result.current.confirmDialog();
    });
    expect(mutateAsyncMock).toHaveBeenCalledWith(
      expect.objectContaining({
        aisleId: 'aisle-1',
        processingMode: 'AUTO',
      })
    );
    expect(mutateAsyncMock.mock.calls[0][0].identificationMode).toBeUndefined();
  });

  it('sends CODE_SCAN_ONLY when selected', async () => {
    const { result } = renderHook(
      () => useAisleProcessingFlow({ inventoryId: 'inv-1', isProductionInventory: false }),
      { wrapper }
    );
    await act(async () => {
      result.current.requestProcess('aisle-1', 'A01', null);
    });
    await act(async () => {
      result.current.setProcessingMode('CODE_SCAN_ONLY');
    });
    await act(async () => {
      await result.current.confirmDialog();
    });
    expect(mutateAsyncMock).toHaveBeenCalledWith(
      expect.objectContaining({ processingMode: 'CODE_SCAN_ONLY' })
    );
  });

  it('dialog shows three modes and confirms VISION_ONLY payload', async () => {
    render(
      <ProcessingHarness
        identification={{ effectiveMode: 'CODE_SCAN', source: 'CLIENT' }}
      />,
      { wrapper }
    );
    fireEvent.mouseDown(within(screen.getByTestId('process-processing-mode')).getByRole('combobox'));
    fireEvent.click(screen.getByTestId('process-processing-mode-vision_only'));
    await act(async () => {
      fireEvent.click(screen.getByTestId('process-aisle-confirm'));
    });
    expect(mutateAsyncMock).toHaveBeenCalledWith(
      expect.objectContaining({ processingMode: 'VISION_ONLY' })
    );
  });
});
