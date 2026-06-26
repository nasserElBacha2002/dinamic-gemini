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
const RECORD_ONLY_MSG = /evidence records exist|registros de evidencia/i;
const IMAGE_LOAD_ERROR_MSG = /could not be loaded|no se pudo cargar la imagen de evidencia/i;

describe('ResultEvidenceViewer', () => {
  beforeEach(() => {
    mockUseEvidenceImageLoad.mockReset();
    mockUseEvidenceImageLoad.mockReturnValue({ status: 'idle' });
  });

  it('VALID + structural evidenceView renders inline preview using backend imageUrl', () => {
    renderViewer(
      baseResult({
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/evidence.jpg',
        },
      })
    );

    expect(screen.getByTestId('result-evidence-inline-preview')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /photo\.jpg|vista previa/i })).toHaveAttribute(
      'src',
      'https://cdn.example/evidence.jpg'
    );
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
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
    expect(screen.queryByTestId('result-evidence-inline-preview')).not.toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
  });

  it('MISSING shows missing message and no inline preview', () => {
    renderViewer(
      baseResult({
        traceabilityStatus: 'MISSING',
        sourceImageId: null,
        hasValidEvidence: false,
      })
    );

    expect(screen.getByText(MISSING_MSG)).toBeInTheDocument();
    expect(screen.queryByTestId('result-evidence-inline-preview')).not.toBeInTheDocument();
  });

  it('UNVALIDATED shows unvalidated message and no inline preview', () => {
    renderViewer(
      baseResult({
        traceabilityStatus: 'UNVALIDATED',
        hasValidEvidence: false,
      })
    );

    expect(screen.getByText(UNVALIDATED_MSG)).toBeInTheDocument();
    expect(screen.queryByTestId('result-evidence-inline-preview')).not.toBeInTheDocument();
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

    expect(screen.queryByTestId('result-evidence-inline-preview')).not.toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
  });

  it('Phase 4.8: evidenceView.displayable=false blocks preview even with sourceImageId', () => {
    renderViewer(
      baseResult({
        traceabilityStatus: 'VALID',
        hasValidEvidence: true,
        sourceImageId: 'asset-1',
        evidenceView: {
          displayable: false,
          traceabilityStatus: 'invalid',
          sourceKind: 'structural_result_evidence',
        },
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

    expect(screen.queryByTestId('result-evidence-inline-preview')).not.toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
  });

  it('Phase 4.8: evidenceView.displayable=true with imageUrl shows inline preview', () => {
    renderViewer(
      baseResult({
        traceabilityStatus: 'INVALID',
        hasValidEvidence: false,
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/evidence.jpg',
        },
      })
    );

    expect(screen.getByTestId('result-evidence-inline-preview')).toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
  });

  it('displayable true without imageUrl shows url unavailable, not record-only', () => {
    renderViewer(
      baseResult({
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: null,
          imageAccessStatus: 'url_unavailable',
        },
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

    expect(screen.getByText(/evidence image is unavailable|imagen de evidencia no está disponible/i)).toBeInTheDocument();
    expect(screen.queryByTestId('result-evidence-inline-preview')).not.toBeInTheDocument();
  });

  it('Phase 4.8: displayable false with imageUrl does not render image or call legacy loader', () => {
    renderViewer(
      baseResult({
        sourceImageId: 'asset-1',
        evidenceView: {
          displayable: false,
          traceabilityStatus: 'invalid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/evidence.jpg',
        },
      })
    );

    expect(screen.queryByTestId('result-evidence-inline-preview')).not.toBeInTheDocument();
    expect(mockUseEvidenceImageLoad).toHaveBeenCalledWith(null);
  });

  it('opens generic fullscreen preview from inline image and fullscreen action', () => {
    renderViewer(
      baseResult({
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/evidence.jpg',
        },
      })
    );

    fireEvent.click(screen.getByTestId('result-evidence-open-fullscreen'));
    expect(screen.getByTestId('image-preview-dialog')).toBeInTheDocument();
  });

  it('shows fallback when direct structural image URL fails to load', () => {
    renderViewer(
      baseResult({
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/broken.jpg',
        },
      })
    );

    const img = screen.getByRole('img', { name: /photo\.jpg|evidence preview/i });
    fireEvent.error(img);

    expect(screen.getByText(IMAGE_LOAD_ERROR_MSG)).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /photo\.jpg|evidence preview/i })).not.toBeInTheDocument();
    expect(screen.getByTestId('result-evidence-open-fullscreen')).toBeDisabled();

    fireEvent.click(screen.getByTestId('result-evidence-open-fullscreen'));
    expect(screen.queryByTestId('image-preview-dialog')).not.toBeInTheDocument();
  });

  it('clears direct image load error when structural image URL changes', () => {
    const { rerender } = renderViewer(
      baseResult({
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/broken.jpg',
        },
      })
    );

    fireEvent.error(screen.getByRole('img', { name: /photo\.jpg|evidence preview/i }));
    expect(screen.getByText(IMAGE_LOAD_ERROR_MSG)).toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <ResultEvidenceViewer
          result={baseResult({
            evidenceView: {
              displayable: true,
              traceabilityStatus: 'valid',
              sourceKind: 'structural_result_evidence',
              imageUrl: 'https://cdn.example/fixed.jpg',
            },
          })}
          inventoryId="inv-1"
          aisleId="aisle-1"
        />
      </ThemeProvider>
    );

    expect(screen.queryByText(IMAGE_LOAD_ERROR_MSG)).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: /photo\.jpg|evidence preview/i })).toHaveAttribute(
      'src',
      'https://cdn.example/fixed.jpg'
    );
  });

  it('clears preview dialog when transitioning VALID to INVALID', () => {
    const { rerender } = renderViewer(
      baseResult({
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/evidence.jpg',
        },
      })
    );

    fireEvent.click(screen.getByTestId('result-evidence-open-fullscreen'));
    expect(screen.getByTestId('image-preview-dialog')).toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <ResultEvidenceViewer
          result={baseResult({
            traceabilityStatus: 'INVALID',
            hasValidEvidence: false,
            evidenceView: {
              displayable: false,
              traceabilityStatus: 'invalid',
              sourceKind: 'structural_result_evidence',
            },
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
    const { rerender } = renderViewer(
      baseResult({
        evidenceView: {
          displayable: true,
          traceabilityStatus: 'valid',
          sourceKind: 'structural_result_evidence',
          imageUrl: 'https://cdn.example/evidence.jpg',
        },
      })
    );

    fireEvent.click(screen.getByTestId('result-evidence-open-fullscreen'));
    expect(screen.getByTestId('image-preview-dialog')).toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <ResultEvidenceViewer
          result={baseResult({
            traceabilityStatus: 'MISSING',
            sourceImageId: null,
            hasValidEvidence: false,
            evidenceView: {
              displayable: false,
              traceabilityStatus: 'missing',
              sourceKind: 'structural_result_evidence',
            },
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
