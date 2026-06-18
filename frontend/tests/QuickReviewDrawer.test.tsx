/**
 * Canonical review drawer — evidence, actions, prev/next (detail loaded via useResultDetail).
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import QuickReviewDrawer from '../src/features/reviewQueue/components/QuickReviewDrawer';
import type { QuickReviewContext } from '../src/features/reviewQueue/quickReviewContext';
import { mapPositionDetailToResultDetail } from '../src/features/results/mappers/positionToResult';
import type { ResultDetail } from '../src/features/results/types';
import { ApiError } from '../src/api/types';
import type { PositionDetailResponse, PositionSummary } from '../src/api/types';

const reviewMutateAsync = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const showSnackbarMock = vi.hoisted(() => vi.fn());
const submitReviewPositionIds = vi.hoisted(() => [] as string[]);
const detailHookPositionIds = vi.hoisted(() => [] as string[]);

const basePosition = {
  id: 'pos-1',
  aisle_id: 'aisle-1',
  status: 'detected',
  position_code: 'P1',
  sku: 'SKU001',
  confidence: 0.9,
  needs_review: false,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  has_evidence: false,
  qty: 1,
  qtySource: 'detected' as const,
};

type UseResultDetailReturn = ReturnType<
  typeof import('../src/features/results').useResultDetail
>;

/** Minimal useResultDetail stub — full UseQueryResult shape not required in component tests. */
function stubUseResultDetail(options: {
  result?: ResultDetail;
  isLoading?: boolean;
  isError?: boolean;
  error?: Error | null;
  refetch?: () => void;
}): UseResultDetailReturn {
  return {
    result: options.result,
    isLoading: options.isLoading ?? false,
    isError: options.isError ?? false,
    error: options.error ?? null,
    refetch: options.refetch ?? vi.fn(),
  } as unknown as UseResultDetailReturn;
}

function createDetailData(
  position: Partial<PositionSummary> & Pick<PositionSummary, 'id'>,
  runContext?: PositionDetailResponse['run_context']
): PositionDetailResponse {
  return {
    position: { ...basePosition, ...position } as PositionSummary,
    evidences: [],
    review_actions: [],
    run_context: runContext ?? {
      job_id: null,
      result_context_source: 'legacy',
      resolved_job_id: null,
    },
  };
}

vi.mock('../src/features/results', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/features/results')>();
  return {
    ...actual,
    useResultDetail: vi.fn(),
  };
});

vi.mock('../src/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/hooks')>();
  return {
    ...actual,
    useSubmitReviewAction: (_inventoryId: string, _aisleId: string, positionId: string) => {
      submitReviewPositionIds.push(positionId);
      return {
        mutateAsync: reviewMutateAsync,
        isPending: false,
        isError: false,
        error: null,
      };
    },
  };
});

vi.mock('../src/features/aisle-code-scans/components/PositionCodeScanEvidenceSection', () => ({
  default: () => <div data-testid="position-code-scan-evidence">Evidencia de código</div>,
}));

vi.mock('../src/components/ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/components/ui')>();
  return {
    ...actual,
    useAppSnackbar: () => ({
      showSnackbar: showSnackbarMock,
      closeSnackbar: vi.fn(),
    }),
  };
});

const baseContext: QuickReviewContext = {
  inventoryId: 'inv-1',
  inventoryName: 'Test Inventory',
  aisleCode: 'A-01',
  aisleId: 'aisle-1',
  positionId: 'pos-1',
  resultIds: ['pos-1'],
  returnTo: 'aisle_results',
};

function renderDrawer(
  context: QuickReviewContext | null,
  options?: { open?: boolean; onClose?: () => void }
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuickReviewDrawer
        open={options?.open ?? Boolean(context)}
        context={context}
        onClose={options?.onClose ?? (() => {})}
      />
    </QueryClientProvider>
  );
}

function mockDetailByPositionId() {
  const skuById: Record<string, string> = {
    'pos-a': 'SKU-A',
    'pos-b': 'SKU-B',
    'pos-c': 'SKU-C',
    'pos-1': 'SKU001',
  };
  return (
    _inv: string | undefined,
    _aisle: string | undefined,
    positionId: string | undefined,
    opts?: { enabled?: boolean; jobId?: string | null; exactPosition?: boolean }
  ) => {
    if (opts?.enabled !== false && positionId) {
      detailHookPositionIds.push(positionId);
    }
    const id = positionId ?? 'pos-1';
    const sku = skuById[id] ?? 'SKU001';
    return stubUseResultDetail({ result: mockResultDetail({ id, sku }) });
  };
}

function mockResultDetail(overrides: Partial<ReturnType<typeof mapPositionDetailToResultDetail>> = {}) {
  const data = createDetailData(basePosition);
  const result = mapPositionDetailToResultDetail(data);
  return { ...result, ...overrides };
}

function mockResultDetailFromApi(
  positionOverrides: Parameters<typeof createDetailData>[0],
  runContext?: PositionDetailResponse['run_context'],
  resultOverrides: Partial<ReturnType<typeof mapPositionDetailToResultDetail>> = {}
) {
  const data = createDetailData(positionOverrides, runContext);
  return { ...mapPositionDetailToResultDetail(data), ...resultOverrides };
}

describe('QuickReviewDrawer', () => {
  beforeEach(() => {
    reviewMutateAsync.mockClear();
    showSnackbarMock.mockClear();
    submitReviewPositionIds.length = 0;
    detailHookPositionIds.length = 0;
  });

  it('review POST job_id uses storage row only, not drawer run_context jobId', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(
      stubUseResultDetail({
        result: mockResultDetailFromApi(
          { ...basePosition, job_id: 'row-storage-job' },
          {
            job_id: 'different-slice-job',
            result_context_source: 'explicit',
            resolved_job_id: 'resolved-other',
          }
        ),
      })
    );

    renderDrawer({ ...baseContext, jobId: 'url-filter-job' });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /confirmar resultado|confirm result/i }));
    expect(reviewMutateAsync).toHaveBeenCalledWith({
      action_type: 'confirm',
      job_id: 'row-storage-job',
    });
  });

  it('Wrong image triggers mark_image_mismatch mutation', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /imagen incorrecta|wrong image/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'mark_image_mismatch' });
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('Imagen incorrecta', 'success');
  });

  it('image mismatch state uses evidence copy, not result-data error wording', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(
      stubUseResultDetail({ result: mockResultDetail({ reviewStatus: 'IMAGE_MISMATCH' }) })
    );

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(
      screen.getByText(/evidencia visual está marcada|visual evidence is marked/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/dato del resultado puede seguir|result data may still/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/El resultado está marcado como imagen incorrecta/i)).toBeNull();
    expect(screen.queryByText(/result is marked as.*wrong image/i)).toBeNull();
  });

  it('confirm result triggers exactly one mutation request', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /confirmar resultado|confirm result/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'confirm' });
    expect(reviewMutateAsync.mock.calls[0][0]).not.toHaveProperty('job_id');
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('Confirmado', 'success');
  });

  it('rapid double-click confirm still triggers only one mutation', async () => {
    let resolveMutate: (() => void) | undefined;
    const mutatePromise = new Promise<void>((resolve) => {
      resolveMutate = resolve;
    });
    reviewMutateAsync.mockImplementationOnce(() => mutatePromise);

    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    const confirmBtn = screen.getByRole('button', { name: /confirmar resultado|confirm result/i });
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    resolveMutate?.();
  });

  it('update quantity triggers exactly one mutation request', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /corregir cantidad|correct quantity/i }));
    fireEvent.change(screen.getByPlaceholderText(/qty placeholder|cantidad/i), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar|save/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({
      action_type: 'update_quantity',
      corrected_quantity: 5,
    });
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('Cantidad actualizada', 'success');
  });

  it('update SKU triggers exactly one mutation request', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /corregir sku|correct sku/i }));
    fireEvent.change(screen.getByPlaceholderText(/update sku|nuevo sku|actualizar sku/i), {
      target: { value: 'NEW-SKU' },
    });
    fireEvent.click(screen.getByRole('button', { name: /guardar|save/i }));
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({
      action_type: 'update_sku',
      sku: 'NEW-SKU',
    });
    await waitFor(() => {
      expect(showSnackbarMock).toHaveBeenCalledTimes(1);
    });
    expect(showSnackbarMock).toHaveBeenCalledWith('SKU actualizado', 'success');
  });

  it('mark invalid confirm shows inline error in dialog when mutation fails', async () => {
    reviewMutateAsync.mockRejectedValueOnce(new ApiError('Not allowed', 403));
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /marcar resultado como inválido|mark result invalid/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(dialog).getByRole('button', { name: /marcar como inválido|mark invalid cta/i }),
    );
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/prohibido|ocurrió|something went wrong|not allowed|could not complete|acceso denegado/i);
    expect(reviewMutateAsync).toHaveBeenCalledTimes(1);
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'delete_position' });
  });

  it('shows Result heading when result loads', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    const heading = await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(heading).toBeInTheDocument();
  });

  it('shows Evidence and source filename when present', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(
      stubUseResultDetail({
        result: mockResultDetail({
          sourceImageId: 'img_002',
          sourceFileName: 'IMG_1024.JPG',
          evidenceView: {
            displayable: true,
            traceabilityStatus: 'valid',
            sourceKind: 'structural_result_evidence',
            imageUrl: 'https://cdn.example/IMG_1024.JPG',
          },
        }),
      })
    );

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/sección de evidencia|evidence section/i)).toBeInTheDocument();
    expect(screen.getByText(/IMG_1024.JPG/)).toBeInTheDocument();
  });

  it('shows Preview when structural evidenceView is displayable', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(
      stubUseResultDetail({
        result: mockResultDetail({
          sourceImageId: 'asset-uuid-123',
          evidenceView: {
            displayable: true,
            traceabilityStatus: 'valid',
            sourceKind: 'structural_result_evidence',
            imageUrl: 'https://cdn.example/asset-uuid-123.jpg',
          },
        }),
      })
    );

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(
      screen.getByRole('button', { name: /preview|vista previa|view full image|ver imagen/i })
    ).toBeInTheDocument();
  });

  it('shows no-evidence state when no source image', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(
      stubUseResultDetail({
        result: mockResultDetail({
          sourceImageId: null,
          sourceFileName: null,
          evidence: [],
        }),
      })
    );

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/sección de evidencia|evidence section/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /preview|vista previa|view full image|ver imagen/i })
    ).toBeNull();
  });

  it('opens shared confirm dialog when Mark result invalid is clicked', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    fireEvent.click(screen.getByRole('button', { name: /marcar resultado como inválido|mark result invalid/i }));
    expect(
      await screen.findByRole('heading', { name: /marcar como inválido|mark invalid title/i }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
  });

  it('shows review controls: confirm and wrong-image action', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByRole('button', { name: /confirmar resultado|confirm result/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /imagen incorrecta|wrong image/i })).toBeInTheDocument();
  });

  it('renders result navigation before confirm when multiple results', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer({
      ...baseContext,
      positionId: 'pos-1',
      resultIds: ['pos-0', 'pos-1', 'pos-2'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(
      screen.getByRole('navigation', { name: /navegación de resultados|result navigation/i })
    ).toBeInTheDocument();
    const positionLabel = screen.getByText(/resultado 2 de 3|result 2 of 3/i);
    const confirmBtn = screen.getByRole('button', { name: /confirmar resultado|confirm result/i });
    expect(
      positionLabel.compareDocumentPosition(confirmBtn) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('shows prev/next when resultIds has multiple and position is in list', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer({
      ...baseContext,
      positionId: 'pos-1',
      resultIds: ['pos-0', 'pos-1', 'pos-2'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/resultado 2 de 3|result 2 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resultado anterior|previous result/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /siguiente resultado|next result/i })).toBeInTheDocument();
  });

  it('hides prev/next when only one id in list', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer({ ...baseContext, resultIds: ['pos-1'] });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.queryByText(/result(ado)? \d+ (de|of) \d+/i)).not.toBeInTheDocument();
  });

  it('hides prev/next when current id not in resultIds', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer({
      ...baseContext,
      positionId: 'pos-1',
      resultIds: ['other-1', 'other-2'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.queryByText(/result(ado)? \d+ (de|of) \d+/i)).not.toBeInTheDocument();
  });

  it('first of three disables Previous', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(stubUseResultDetail({ result: mockResultDetail() }));

    renderDrawer({
      ...baseContext,
      positionId: 'pos-1',
      resultIds: ['pos-1', 'pos-2', 'pos-3'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/resultado 1 de 3|result 1 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resultado anterior|previous result/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /siguiente resultado|next result/i })).not.toBeDisabled();
  });

  it('after A → B → close → open C loads C not stale B', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockImplementation(mockDetailByPositionId());

    const navContext: QuickReviewContext = {
      ...baseContext,
      positionId: 'pos-a',
      resultIds: ['pos-a', 'pos-b', 'pos-c'],
      exactPositionDetail: true,
    };

    const { rerender } = renderDrawer(navContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU-A' });

    fireEvent.click(screen.getByRole('button', { name: /siguiente resultado|next result/i }));
    await screen.findByRole('heading', { level: 1, name: 'SKU-B' });

    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <QuickReviewDrawer open={false} context={null} onClose={() => {}} />
      </QueryClientProvider>
    );

    detailHookPositionIds.length = 0;
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <QuickReviewDrawer
          open
          context={{ ...navContext, positionId: 'pos-c' }}
          onClose={() => {}}
        />
      </QueryClientProvider>
    );

    await screen.findByRole('heading', { level: 1, name: 'SKU-C' });
    expect(screen.queryByRole('heading', { level: 1, name: 'SKU-B' })).toBeNull();
    expect(detailHookPositionIds).toContain('pos-c');
    expect(detailHookPositionIds).not.toContain('pos-b');
  });

  it('confirm on internally navigated B targets position B', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockImplementation(mockDetailByPositionId());

    renderDrawer({
      ...baseContext,
      positionId: 'pos-a',
      resultIds: ['pos-a', 'pos-b'],
      exactPositionDetail: true,
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU-A' });
    fireEvent.click(screen.getByRole('button', { name: /siguiente resultado|next result/i }));
    await screen.findByRole('heading', { level: 1, name: 'SKU-B' });

    fireEvent.click(screen.getByRole('button', { name: /confirmar resultado|confirm result/i }));
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'confirm' });
    expect(submitReviewPositionIds.at(-1)).toBe('pos-b');
  });

  it('open drawer resyncs when parent selected result changes after internal navigation', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockImplementation(mockDetailByPositionId());

    const navContext: QuickReviewContext = {
      ...baseContext,
      positionId: 'pos-a',
      resultIds: ['pos-a', 'pos-b', 'pos-c'],
      exactPositionDetail: true,
    };

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <QuickReviewDrawer open context={navContext} onClose={() => {}} />
      </QueryClientProvider>
    );

    await screen.findByRole('heading', { level: 1, name: 'SKU-A' });
    fireEvent.click(screen.getByRole('button', { name: /siguiente resultado|next result/i }));
    await screen.findByRole('heading', { level: 1, name: 'SKU-B' });

    submitReviewPositionIds.length = 0;
    detailHookPositionIds.length = 0;

    rerender(
      <QueryClientProvider client={client}>
        <QuickReviewDrawer
          open
          context={{ ...navContext, positionId: 'pos-c' }}
          onClose={() => {}}
        />
      </QueryClientProvider>
    );

    await screen.findByRole('heading', { level: 1, name: 'SKU-C' });
    expect(screen.queryByRole('heading', { level: 1, name: 'SKU-B' })).toBeNull();
    expect(detailHookPositionIds).toContain('pos-c');

    fireEvent.click(screen.getByRole('button', { name: /confirmar resultado|confirm result/i }));
    expect(reviewMutateAsync).toHaveBeenCalledWith({ action_type: 'confirm' });
    expect(submitReviewPositionIds.at(-1)).toBe('pos-c');
  });

  it('last of three disables Next', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(
      stubUseResultDetail({ result: mockResultDetail({ id: 'pos-3' }) })
    );

    renderDrawer({
      ...baseContext,
      positionId: 'pos-3',
      resultIds: ['pos-1', 'pos-2', 'pos-3'],
    });
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByText(/resultado 3 de 3|result 3 of 3/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resultado anterior|previous result/i })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /siguiente resultado|next result/i })).toBeDisabled();
  });

  it('renders code scan evidence section when result is loaded', async () => {
    const { useResultDetail } = await import('../src/features/results');
    vi.mocked(useResultDetail).mockReturnValue(
      stubUseResultDetail({ result: mockResultDetail() })
    );
    renderDrawer(baseContext);
    await screen.findByRole('heading', { level: 1, name: 'SKU001' });
    expect(screen.getByTestId('position-code-scan-evidence')).toBeInTheDocument();
    expect(screen.getByText('Evidencia de código')).toBeInTheDocument();
  });
});
