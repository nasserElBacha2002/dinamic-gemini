import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { CodeScanRunSummary, CodeScanSummaryItem } from '../../../src/api/types/codeScans';
import CodeScanDrawer from '../../../src/features/aisle-code-scans/components/CodeScanDrawer';
import { AppSnackbarProvider } from '../../../src/components/ui';

const mockRun: CodeScanRunSummary = {
  id: 'run-1',
  status: 'completed_with_warnings',
  total_assets: 10,
  processed_assets: 8,
  failed_assets: 2,
  total_codes_found: 3,
  total_qr_found: 1,
  total_barcodes_found: 2,
  started_at: '2026-05-20T12:00:00Z',
  finished_at: '2026-05-20T12:00:10Z',
  scanner_engine: 'pyzbar',
  error_message: null,
  warnings: ['No se pudo leer el activo asset-3'],
};

const mockDetections = [
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
    metadata_json: { pyzbar_type: 'EAN13' },
    matched_position_id: 'pos-abc',
    match_status: 'matched',
    match_type: 'barcode_exact',
    match_confidence: 1,
    match_metadata_json: { matched_field: 'position_barcode' },
    matched_at: '2026-05-20T12:00:05Z',
  },
  {
    id: 'det-2',
    run_id: 'run-1',
    asset_id: 'asset-2',
    code_type: 'qr',
    code_value: 'UNKNOWN',
    normalized_code_value: 'UNKNOWN',
    detection_status: 'detected',
    confidence: null,
    bounding_box_json: null,
    scanner_engine: 'pyzbar',
    created_at: '2026-05-20T12:00:06Z',
    metadata_json: null,
    matched_position_id: null,
    match_status: 'no_match',
    match_type: 'no_match',
    match_confidence: 0,
    match_metadata_json: null,
    matched_at: '2026-05-20T12:00:06Z',
  },
];

const mockSummaryItems: CodeScanSummaryItem[] = [
  {
    code_value: '7791234567890',
    normalized_code_value: '7791234567890',
    code_type: 'barcode',
    occurrences: 1,
    asset_ids: ['asset-1'],
    first_seen_at: '2026-05-20T12:00:05Z',
    match_status: 'matched',
    matched_position_ids: ['pos-abc'],
    match_types: ['barcode_exact'],
  },
];

const scansState = vi.hoisted(() => ({
  data: { latest_run: null as typeof mockRun | null, detections: [] as typeof mockDetections },
  isLoading: false,
  isError: false,
  error: null as unknown,
}));

const summaryState = vi.hoisted(() => ({
  data: { latest_run: null as typeof mockRun | null, items: [] as typeof mockSummaryItems },
  isLoading: false,
  isError: false,
  error: null as unknown,
}));

const mutateAsync = vi.hoisted(() => vi.fn().mockResolvedValue({ run: { id: 'run-1' } }));

vi.mock('../../../src/features/aisle-code-scans/hooks/useAisleCodeScans', () => ({
  useAisleCodeScans: () => ({
    ...scansState,
    refetch: vi.fn(),
  }),
  useAisleCodeScanSummary: () => ({
    ...summaryState,
    refetch: vi.fn(),
  }),
}));

vi.mock('../../../src/features/aisle-code-scans/hooks/useRunAisleCodeScan', () => ({
  useRunAisleCodeScan: () => ({
    mutateAsync,
    isPending: false,
  }),
}));

vi.mock('../../../src/features/aisle-code-scans/components/CodeScanAssetPreviewButton', () => ({
  default: () => <button type="button">Ver imagen</button>,
}));

vi.mock('../../../src/features/aisle-code-scans/components/CodeScanReviewSignals', () => ({
  default: () => <div data-testid="code-scan-review-signals-mock" />,
}));

vi.mock('../../../src/features/aisle-code-scans/components/CodeScanExportMenu', () => ({
  default: () => <button type="button">Exportar</button>,
}));

function renderDrawer(open = true) {
  return render(
    <AppSnackbarProvider>
      <CodeScanDrawer
        open={open}
        onClose={vi.fn()}
        inventoryId="inv-1"
        aisleId="aisle-1"
      />
    </AppSnackbarProvider>
  );
}

describe('CodeScanDrawer', () => {
  beforeEach(() => {
    scansState.data = { latest_run: null, detections: [] };
    scansState.isLoading = false;
    scansState.isError = false;
    summaryState.data = { latest_run: null, items: [] };
    summaryState.isLoading = false;
    summaryState.isError = false;
    mutateAsync.mockClear();
  });

  it('shows no-run empty state with a single scan CTA', () => {
    renderDrawer();
    expect(screen.getByText(/Todavía no se escanearon códigos/i)).toBeInTheDocument();
    const scanButtons = screen.getAllByRole('button', { name: /Escanear códigos/i });
    expect(scanButtons).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /Re-escanear/i })).not.toBeInTheDocument();
  });

  it('shows latest run summary and warnings', () => {
    scansState.data = { latest_run: mockRun, detections: mockDetections };
    summaryState.data = { latest_run: mockRun, items: mockSummaryItems };
    renderDrawer();
    expect(screen.getByText(/Códigos detectados/i)).toBeInTheDocument();
    expect(screen.getByText(/Completado con advertencias/i)).toBeInTheDocument();
    expect(screen.getByText(/El escaneo finalizó con advertencias/i)).toBeInTheDocument();
    expect(screen.getAllByText('7791234567890').length).toBeGreaterThan(0);
  });

  it('shows no-detections state when run has zero codes', () => {
    scansState.data = {
      latest_run: { ...mockRun, total_codes_found: 0, warnings: [] },
      detections: [],
    };
    summaryState.data = { latest_run: scansState.data.latest_run, items: [] };
    renderDrawer();
    expect(screen.getByText(/No se detectaron códigos/i)).toBeInTheDocument();
  });

  it('shows re-scan in header when latest run exists', () => {
    scansState.data = { latest_run: mockRun, detections: mockDetections };
    summaryState.data = { latest_run: mockRun, items: mockSummaryItems };
    renderDrawer();
    expect(screen.getByRole('button', { name: /Re-escanear/i })).toBeInTheDocument();
    expect(screen.queryByText(/Todavía no se escanearon códigos/i)).not.toBeInTheDocument();
  });

  it('asks confirmation before re-run', async () => {
    scansState.data = { latest_run: mockRun, detections: mockDetections };
    summaryState.data = { latest_run: mockRun, items: mockSummaryItems };
    renderDrawer();
    fireEvent.click(screen.getByRole('button', { name: /Re-escanear/i }));
    expect(screen.getByText(/Reemplazar escaneo anterior/i)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /Re-escanear/i }).pop()!);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
  });

  it('shows error state', () => {
    scansState.isError = true;
    scansState.error = new Error('load failed');
    renderDrawer();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('shows match status labels without validated wording', () => {
    scansState.data = {
      latest_run: {
        ...mockRun,
        metadata_json: {
          matching: { status: 'completed', scope: 'job', job_id: 'job-1' },
        },
      },
      detections: mockDetections,
    };
    summaryState.data = {
      latest_run: scansState.data.latest_run,
      items: [
        {
          ...mockSummaryItems[0],
          match_status: 'mixed',
          match_status_counts: { matched: 1, no_match: 1 },
        },
      ],
    };
    render(
      <AppSnackbarProvider>
        <CodeScanDrawer
          open
          onClose={vi.fn()}
          inventoryId="inv-1"
          aisleId="aisle-1"
          jobIdForMatching="job-1"
        />
      </AppSnackbarProvider>,
    );
    expect(screen.getAllByText(/Coincidencia sugerida/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Sin coincidencia/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Validado/i)).not.toBeInTheDocument();
    expect(screen.getAllByText('pos-abc').length).toBeGreaterThan(0);
    expect(screen.getByText(/Coincidencias evaluadas sobre la corrida seleccionada/i)).toBeInTheDocument();
    expect(screen.getByText(/Coincidencia mixta/i)).toBeInTheDocument();
  });
});
