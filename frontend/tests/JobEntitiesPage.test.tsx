/**
 * Epic 3.1.B / Epic 4 — Job entities page and traceability display tests.
 * Covers loading, empty, error, populated, legacy (optional fields absent), and Epic 4 display-label fallback behavior.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import JobEntitiesPage from '../src/pages/JobEntitiesPage';

vi.mock('../src/api/client', () => ({ getJobEntities: vi.fn() }));
import { getJobEntities } from '../src/api/client';

const mockGetJobEntities = vi.mocked(getJobEntities);

function renderWithProviders(initialRoute = '/job-entities/job-123') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/job-entities/:jobId" element={<JobEntitiesPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('JobEntitiesPage', () => {
  beforeEach(() => {
    mockGetJobEntities.mockReset();
  });

  it('shows loading state initially', () => {
    mockGetJobEntities.mockImplementation(() => new Promise(() => {}));
    renderWithProviders();
    expect(screen.getByText(/loading count results/i)).toBeInTheDocument();
  });

  it('shows empty state when job has no entities', async () => {
    mockGetJobEntities.mockResolvedValue({ entities: [] });
    renderWithProviders();
    await screen.findByText(/no count results for this job yet/i);
    expect(mockGetJobEntities).toHaveBeenCalledWith('job-123', { traceability_status: undefined });
  });

  it('shows error state when request fails', async () => {
    mockGetJobEntities.mockRejectedValue(new Error('Network error'));
    renderWithProviders();
    await screen.findByText(/failed to load count results|network error/i);
  });

  it('renders entity list with traceability fields', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [
        {
          entity_uid: 'e1',
          pallet_id: 'p1',
          entity_type: 'product',
          count_status: 'counted',
          source_image_id: 'img_001',
          traceability_status: 'valid',
          traceability_warning: null,
          review_display_label: 'SKU-001',
        },
        {
          entity_uid: 'e2',
          pallet_id: null,
          entity_type: 'product',
          count_status: null,
          source_image_id: null,
          traceability_status: 'missing',
          traceability_warning: null,
          review_display_label: null,
        },
      ],
    });
    renderWithProviders();
    await screen.findByText('e1');
    expect(screen.getByText('SKU-001')).toBeInTheDocument();
    expect(screen.getByText('img_001')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Valid' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Missing' })).toBeInTheDocument();
    const validChips = screen.getAllByText('Valid');
    expect(validChips.length).toBeGreaterThanOrEqual(1);
    const missingLabels = screen.getAllByText('Missing');
    expect(missingLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('e2')).toBeInTheDocument();
  });

  it('renders traceability summary block when backend returns traceability_summary', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [
        { entity_uid: 'e1', entity_type: 'PALLET', traceability_status: 'valid' },
      ],
      traceability_summary: {
        total_entities: 3,
        valid: 1,
        missing: 1,
        invalid: 1,
        unvalidated: 0,
      },
    });
    renderWithProviders();
    await screen.findByText('e1');
    expect(screen.getByText(/Traceability \(job total\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Total 3/)).toBeInTheDocument();
    expect(screen.getByText(/Valid 1/)).toBeInTheDocument();
    expect(screen.getByText(/Missing 1/)).toBeInTheDocument();
    expect(screen.getByText(/Invalid 1/)).toBeInTheDocument();
    expect(screen.getByText(/Unvalidated 0/)).toBeInTheDocument();
  });

  it('does not render traceability summary when absent (legacy response)', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [{ entity_uid: 'e1', entity_type: 'PALLET' }],
    });
    renderWithProviders();
    await screen.findByText('e1');
    expect(screen.queryByText(/Traceability \(job total\)/i)).not.toBeInTheDocument();
  });

  it('calls getJobEntities with traceability_status when filter tab is selected', async () => {
    mockGetJobEntities.mockResolvedValue({ entities: [] });
    renderWithProviders();
    await screen.findByText(/no count results/i);
    expect(mockGetJobEntities).toHaveBeenCalledWith('job-123', { traceability_status: undefined });
    mockGetJobEntities.mockClear();
    const missingTab = screen.getByRole('tab', { name: /missing/i });
    missingTab.click();
    await waitFor(() => {
      expect(mockGetJobEntities).toHaveBeenCalledWith('job-123', { traceability_status: 'missing' });
    });
  });

  it('shows traceability_warning as tooltip on Invalid chip when present', async () => {
    const warningText = 'source_image_id not in job';
    mockGetJobEntities.mockResolvedValue({
      entities: [
        {
          entity_uid: 'e1',
          entity_type: 'PALLET',
          traceability_status: 'invalid',
          traceability_warning: warningText,
        },
      ],
    });
    renderWithProviders();
    await screen.findByText('e1');
    const invalidChips = screen.getAllByText('Invalid');
    const tableChip = invalidChips.find((el) => el.closest('table') !== null) ?? invalidChips[0];
    fireEvent.mouseOver(tableChip);
    await waitFor(() => {
      expect(screen.getByRole('tooltip')).toHaveTextContent(warningText);
    });
  });

  it('shows filter-specific empty message when filter is applied and no entities match', async () => {
    mockGetJobEntities.mockResolvedValue({ entities: [] });
    renderWithProviders();
    await screen.findByText(/no count results/i);
    const missingTab = screen.getByRole('tab', { name: /missing/i });
    missingTab.click();
    await screen.findByText(/no entities match the selected traceability filter/i);
  });

  it('renders legacy entities without traceability (shows em dash)', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [
        {
          entity_uid: 'legacy-1',
          pallet_id: 'pallet-x',
          entity_type: 'product',
          count_status: 'counted',
          source_image_id: undefined,
          traceability_status: undefined,
          traceability_warning: undefined,
        },
      ],
    });
    renderWithProviders();
    await screen.findByText('legacy-1');
    const cells = screen.getAllByRole('cell');
    const traceabilityCells = cells.filter((c) => c.textContent === '—');
    expect(traceabilityCells.length).toBeGreaterThanOrEqual(1);
  });

  it('Epic 4: shows Review label column with review_display_label when present', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [
        {
          entity_uid: 'ent-1',
          entity_type: 'PALLET',
          review_display_label: 'SKU-XYZ',
          product_display_label: 'SKU-XYZ',
        },
      ],
    });
    renderWithProviders();
    await screen.findByText('ent-1');
    expect(screen.getByRole('columnheader', { name: /review label/i })).toBeInTheDocument();
    expect(screen.getByText('SKU-XYZ')).toBeInTheDocument();
  });

  it('Epic 4: prefers review_display_label over product_display_label when both present', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [
        {
          entity_uid: 'ent-1a',
          entity_type: 'PALLET',
          review_display_label: 'PREFERRED',
          product_display_label: 'LEGACY-VAL',
        },
      ],
    });
    renderWithProviders();
    await screen.findByText('ent-1a');
    expect(screen.getByText('PREFERRED')).toBeInTheDocument();
    expect(screen.queryByText('LEGACY-VAL')).not.toBeInTheDocument();
  });

  it('Epic 4: falls back to product_display_label when review_display_label absent (legacy)', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [
        {
          entity_uid: 'ent-2',
          entity_type: 'PALLET',
          product_display_label: 'LEGACY-POS',
        },
      ],
    });
    renderWithProviders();
    await screen.findByText('ent-2');
    expect(screen.getByText('LEGACY-POS')).toBeInTheDocument();
  });

  it('Epic 4: shows em dash for Review label when both fields absent or empty', async () => {
    mockGetJobEntities.mockResolvedValue({
      entities: [
        { entity_uid: 'ent-3', entity_type: 'PALLET' },
        { entity_uid: 'ent-4', entity_type: 'PALLET', review_display_label: '', product_display_label: null },
      ],
    });
    renderWithProviders();
    await screen.findByText('ent-3');
    await screen.findByText('ent-4');
    const cells = screen.getAllByRole('cell');
    const emDashes = cells.filter((c) => c.textContent === '—');
    expect(emDashes.length).toBeGreaterThanOrEqual(2);
  });

  it('shows Inventories link for back fallback', async () => {
    mockGetJobEntities.mockResolvedValue({ entities: [] });
    renderWithProviders();
    await screen.findByText(/no count results/i);
    expect(screen.getByText('Inventories')).toBeInTheDocument();
  });
});
