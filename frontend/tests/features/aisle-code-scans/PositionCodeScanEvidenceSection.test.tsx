import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PositionCodeScanEvidenceSection from '../../../src/features/aisle-code-scans/components/PositionCodeScanEvidenceSection';
import type { PositionCodeScanEvidenceResponse } from '../../../src/api/types/codeScans';

const usePositionCodeScanEvidence = vi.hoisted(() => vi.fn());

vi.mock('../../../src/features/aisle-code-scans/hooks/usePositionCodeScanEvidence', () => ({
  usePositionCodeScanEvidence,
}));

vi.mock('../../../src/features/aisle-code-scans/components/CodeScanAssetPreviewButton', () => ({
  default: () => <button type="button">Ver imagen</button>,
}));

vi.mock('../../../src/features/aisle-code-scans/components/CopyCodeValueButton', () => ({
  default: () => <button type="button">Copiar</button>,
}));

function renderSection(
  hookReturn: Partial<ReturnType<typeof usePositionCodeScanEvidence>> = {}
) {
  usePositionCodeScanEvidence.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...hookReturn,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PositionCodeScanEvidenceSection
        inventoryId="inv-1"
        aisleId="aisle-1"
        positionId="pos-1"
        enabled
      />
    </QueryClientProvider>
  );
}

const evidencePayload: PositionCodeScanEvidenceResponse = {
  latest_run: {
    id: 'run-1',
    status: 'completed',
    total_assets: 1,
    processed_assets: 1,
    failed_assets: 0,
    total_codes_found: 1,
    total_qr_found: 0,
    total_barcodes_found: 1,
    started_at: '2026-05-20T12:00:00Z',
    finished_at: '2026-05-20T12:00:10Z',
    scanner_engine: 'pyzbar',
    error_message: null,
    warnings: [],
  },
  summary: { total_detections: 1, source_assets_count: 1, code_types: { barcode: 1 } },
  detections: [
    {
      id: 'det-1',
      run_id: 'run-1',
      asset_id: 'asset-1',
      code_type: 'barcode',
      code_value: '7791234567890',
      normalized_code_value: '7791234567890',
      detection_status: 'detected',
      confidence: null,
      bounding_box_json: null,
      scanner_engine: 'pyzbar',
      created_at: '2026-05-20T12:00:05Z',
      metadata_json: null,
      matched_position_id: 'pos-1',
      match_status: 'matched',
      match_type: 'sku_exact',
      match_confidence: 1,
      match_metadata_json: null,
      matched_at: '2026-05-20T12:00:06Z',
    },
  ],
};

describe('PositionCodeScanEvidenceSection', () => {
  beforeEach(() => {
    usePositionCodeScanEvidence.mockReset();
  });

  it('renders section title', () => {
    renderSection();
    expect(screen.getByText('Evidencia de código')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    renderSection({ isLoading: true });
    expect(screen.getByText('Cargando evidencia de código...')).toBeInTheDocument();
  });

  it('renders no-run state', () => {
    renderSection({
      data: {
        latest_run: null,
        summary: { total_detections: 0, source_assets_count: 0, code_types: {} },
        detections: [],
      },
    });
    expect(
      screen.getByText('Todavía no hay escaneos de códigos para este pasillo.')
    ).toBeInTheDocument();
  });

  it('renders empty state when run exists but no linked detections', () => {
    renderSection({
      data: {
        latest_run: evidencePayload.latest_run,
        summary: { total_detections: 0, source_assets_count: 0, code_types: {} },
        detections: [],
      },
    });
    expect(
      screen.getByText('No hay códigos detectados vinculados a este resultado.')
    ).toBeInTheDocument();
  });

  it('renders evidence rows with type, value, match and view image', () => {
    renderSection({ data: evidencePayload });
    expect(screen.getByText('Código de barras')).toBeInTheDocument();
    expect(screen.getByText('7791234567890')).toBeInTheDocument();
    expect(screen.getByText('SKU exacto')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ver imagen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copiar' })).toBeInTheDocument();
  });

  it('does not use forbidden validation wording', () => {
    renderSection({ data: evidencePayload });
    const section = screen.getByTestId('position-code-scan-evidence');
    const text = section.textContent ?? '';
    expect(text).not.toMatch(/Validado/i);
    expect(text).not.toMatch(/Confirmado/i);
    expect(text).not.toMatch(/Correcto/i);
    expect(text).not.toMatch(/Aceptado/i);
  });
});
