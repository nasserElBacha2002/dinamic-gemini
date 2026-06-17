/**
 * Phase 4.2 corrections — ResultEvidenceViewer traceability precedence and stale preview cleanup.
 */

import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import theme from '../src/theme';
import ResultEvidenceViewer from '../src/features/results/components/detail/ResultEvidenceViewer';
import type { ResultDetail } from '../src/features/results/types';
import { useEvidenceImageLoad } from '../src/features/results/hooks/useEvidenceImageLoad';

vi.mock('../src/features/results/hooks/useEvidenceImageLoad', () => ({
  useEvidenceImageLoad: vi.fn(() => ({ status: 'idle' as const })),
}));

vi.mock('../src/components/ui', () => ({
  ImageAssetCard: ({
    title,
    actions,
  }: {
    title: string;
    actions?: React.ReactNode;
  }) => (
    <div data-testid="image-asset-card">
      <span>{title}</span>
      {actions}
    </div>
  ),
  ImagePreviewDialog: ({
    open,
    title,
    src,
  }: {
    open: boolean;
    title?: string;
    src?: string | null;
  }) =>
    open ? (
      <div data-testid="image-preview-dialog" aria-label={title}>
        {src ? <img src={src} alt="preview" /> : null}
      </div>
    ) : null,
}));

const mockUseEvidenceImageLoad = vi.mocked(useEvidenceImageLoad);

function baseResult(overrides: Partial<ResultDetail> = {}): ResultDetail {
  return {
    id: 'pos-1',
    sku: 'SKU-1',
    positionCode: 'P1',
    detectedQty: 1,
    correctedQty: null,
    resolvedQty: 1,
    systemQty: 1,
    confidence: 0.9,
    reviewStatus: 'DETECTED',
    traceabilityStatus: 'VALID',
    needsReview: false,
    updatedAt: '2024-01-01T00:00:00Z',
    sourceImageId: 'asset-1',
    sourceFileName: 'photo.jpg',
    hasValidEvidence: true,
    evidence: [],
    reviewHistory: [],
    technicalMetadata: { entityId: 'job-1_E1', primaryEvidenceId: 'ev-1' },
    ...overrides,
  };
}

function renderViewer(result: ResultDetail) {
  return render(
    <ThemeProvider theme={theme}>
      <ResultEvidenceViewer result={result} inventoryId="inv-1" aisleId="aisle-1" />
    </ThemeProvider>
  );
}

const INVALID_MSG = /could not be validated|no se pudo validar la evidencia/i;
const MISSING_MSG = /no evidence image was returned|no devolvió una imagen de evidencia/i;
const UNVALIDATED_MSG = /traceability could not be confirmed|no se pudo confirmar la trazabilidad/i;
const RECORD_ONLY_MSG = /record only|registros de evidencia/i;

describe('ResultEvidenceViewer', () => {
  beforeEach(() => {
    mockUseEvidenceImageLoad.mockReset();
    mockUseEvidenceImageLoad.mockReturnValue({ status: 'idle' });
  });

  it('VALID + hasValidEvidence renders preview actions', () => {
    renderViewer(
      baseResult({
        evidence: [
          {
            id: 'ev-1',
            role: 'PRIMARY',
            sourceImageId: 'crop-1',
            sourceFileName: 'crop.jpg',
            imageUrl: null,
          },
        ],
      })
    );

    expect(screen.getAllByTestId('image-asset-card').length).toBeGreaterThan(0);
    expect(screen.queryByText(INVALID_MSG)).not.toBeInTheDocument();
  });

  it('INVALID with crop records shows invalid message, not record-only', () => {
    renderViewer(
      baseResult({
        traceabilityStatus: 'INVALID',
        hasValidEvidence: false,
        evidence: [
          {
            id: 'ev-1',
            role: 'PRIMARY',
            sourceImageId: 'crop-1',
            sourceFileName: 'crop.jpg',
            imageUrl: null,
          },
        ],
      })
    );

    expect(screen.getByText(INVALID_MSG)).toBeInTheDocument();
    expect(screen.queryByText(RECORD_ONLY_MSG)).not.toBeInTheDocument();
    expect(screen.queryByTestId('image-asset-card')).not.toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
  });

  it('MISSING shows missing message and no preview cards', () => {
    renderViewer(
      baseResult({
        traceabilityStatus: 'MISSING',
        sourceImageId: null,
        hasValidEvidence: false,
      })
    );

    expect(screen.getByText(MISSING_MSG)).toBeInTheDocument();
    expect(screen.queryByTestId('image-asset-card')).not.toBeInTheDocument();
  });

  it('UNVALIDATED shows unvalidated message and no preview cards', () => {
    renderViewer(
      baseResult({
        traceabilityStatus: 'UNVALIDATED',
        hasValidEvidence: false,
      })
    );

    expect(screen.getByText(UNVALIDATED_MSG)).toBeInTheDocument();
    expect(screen.queryByTestId('image-asset-card')).not.toBeInTheDocument();
  });

  it('VALID + hasValidEvidence false blocks preview', () => {
    renderViewer(
      baseResult({
        hasValidEvidence: false,
        evidence: [
          {
            id: 'ev-1',
            role: 'PRIMARY',
            sourceImageId: 'crop-1',
            sourceFileName: 'crop.jpg',
            imageUrl: null,
          },
        ],
      })
    );

    expect(screen.queryByTestId('image-asset-card')).not.toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
  });

  it('valid traceability with previewable assets does not show record-only message', () => {
    renderViewer(
      baseResult({
        evidence: [
          {
            id: 'ev-1',
            role: 'PRIMARY',
            sourceImageId: 'crop-1',
            sourceFileName: 'crop.jpg',
            imageUrl: null,
          },
        ],
      })
    );

    expect(screen.queryByText(RECORD_ONLY_MSG)).not.toBeInTheDocument();
    expect(screen.getAllByTestId('image-asset-card').length).toBeGreaterThan(0);
  });

  it('clears preview dialog when transitioning VALID to INVALID', () => {
    mockUseEvidenceImageLoad.mockReturnValue({
      status: 'loaded',
      imageSrc: 'blob:preview',
    });

    const { rerender } = renderViewer(
      baseResult({
        evidence: [
          {
            id: 'ev-1',
            role: 'PRIMARY',
            sourceImageId: 'crop-1',
            sourceFileName: 'crop.jpg',
            imageUrl: null,
          },
        ],
      })
    );

    fireEvent.click(screen.getAllByRole('button', { name: /preview|vista previa/i })[0]!);
    expect(screen.getByTestId('image-preview-dialog')).toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <ResultEvidenceViewer
          result={baseResult({
            traceabilityStatus: 'INVALID',
            hasValidEvidence: false,
            evidence: [
              {
                id: 'ev-1',
                role: 'PRIMARY',
                sourceImageId: 'crop-1',
                sourceFileName: 'crop.jpg',
                imageUrl: null,
              },
            ],
          })}
          inventoryId="inv-1"
          aisleId="aisle-1"
        />
      </ThemeProvider>
    );

    expect(screen.queryByTestId('image-preview-dialog')).not.toBeInTheDocument();
    expect(screen.getByText(INVALID_MSG)).toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenLastCalledWith(null);
  });

  it('clears preview when transitioning VALID to MISSING', () => {
    mockUseEvidenceImageLoad.mockReturnValue({
      status: 'loaded',
      imageSrc: 'blob:preview',
    });

    const { rerender } = renderViewer(
      baseResult({
        evidence: [
          {
            id: 'ev-1',
            role: 'PRIMARY',
            sourceImageId: 'crop-1',
            sourceFileName: 'crop.jpg',
            imageUrl: null,
          },
        ],
      })
    );

    fireEvent.click(screen.getAllByRole('button', { name: /preview|vista previa/i })[0]!);
    expect(screen.getByTestId('image-preview-dialog')).toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <ResultEvidenceViewer
          result={baseResult({
            traceabilityStatus: 'MISSING',
            sourceImageId: null,
            hasValidEvidence: false,
            evidence: [],
          })}
          inventoryId="inv-1"
          aisleId="aisle-1"
        />
      </ThemeProvider>
    );

    expect(screen.queryByTestId('image-preview-dialog')).not.toBeInTheDocument();
    expect(screen.getByText(MISSING_MSG)).toBeInTheDocument();
  });
});
