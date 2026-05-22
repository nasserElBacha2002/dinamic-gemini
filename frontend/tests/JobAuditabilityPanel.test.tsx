import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '../src/api/client';
import JobAuditabilityPanel from '../src/components/JobAuditabilityPanel';
import type { RunAuditabilityView, LlmCostSnapshot } from '../src/api/types';

function sampleCostSnapshot(): LlmCostSnapshot {
  return {
    provider: 'gemini-audit-cost',
    model: 'gemini-2.5-pro-test',
    billing_currency: 'USD',
    usage: { input_tokens: 12430, output_tokens: 840, total_tokens: 13270 },
    pricing_snapshot: { pricing_source: 'catalog_test', billing_currency: 'USD' },
    computed_cost: {
      subtotal_input: '0.00123000',
      subtotal_output: '0.00840000',
      total_cost: '0.00963000',
      currency: 'USD',
    },
    capture_status: 'estimated',
    capture_notes: ['nota-de-prueba'],
  };
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function fullView(overrides: Partial<RunAuditabilityView> = {}): RunAuditabilityView {
  return {
    job_id: 'j1',
    status: 'succeeded',
    target_type: 'aisle',
    target_id: 'a1',
    created_at: '2026-01-01T00:00:00Z',
    started_at: null,
    finished_at: null,
    inventory_id: 'inv1',
    aisle_id: 'a1',
    client_id: 'c1',
    client_supplier_id: 's1',
    provider_name: 'gemini',
    model_name: 'm1',
    prompt_key: 'pk',
    prompt_version: '1',
    supplier_prompt_config_id: 'spc',
    supplier_prompt_config_version: '2',
    supplier_prompt_fallback_used: false,
    supplier_prompt_fallback_reason: null,
    protected_prompt_contract_key: 'k',
    protected_prompt_contract_version: 'v',
    effective_prompt_hash: 'eff-hash',
    prompt_composition_available: true,
    reference_usage: {
      resolved: true,
      resolved_count: 1,
      provider_consumed: true,
      provider_consumed_count: 1,
      reference_ids: ['r1'],
      resolution_error: null,
    },
    supplier_reference_images_used: true,
    inventory_visual_references_used: null,
    reference_source: 'supplier_reference_images',
    reference_image_count: 1,
    reference_ids: ['r1'],
    warnings: [],
    metadata_sources: {
      job_row: true,
      result_json: true,
      aisle_join: true,
      inventory_join: true,
      hybrid_report: true,
      execution_log: true,
      run_audit_snapshot: false,
    },
    missing_metadata: [],
    legacy_mode: false,
    ...overrides,
  };
}

describe('JobAuditabilityPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Spanish section labels and key values on happy path', () => {
    wrap(
      <JobAuditabilityPanel
        inventoryId="inv1"
        aisleId="a1"
        jobId="j1"
        auditability={fullView()}
      />
    );
    expect(screen.getByText(/auditabilidad del procesamiento/i)).toBeInTheDocument();
    expect(screen.getByText('Resumen')).toBeInTheDocument();
    expect(screen.getByText('Cliente')).toBeInTheDocument();
    expect(screen.getByText('Proveedor del cliente')).toBeInTheDocument();
    expect(screen.getByText('Modelo')).toBeInTheDocument();
    expect(screen.getByText('eff-hash')).toBeInTheDocument();
    expect(screen.getByText('spc')).toBeInTheDocument();
    expect(screen.getByText('Fallback aplicado')).toBeInTheDocument();
    expect(screen.getByText('Fuentes de metadata')).toBeInTheDocument();
  });

  it('shows missing hybrid_report and execution_log without crashing', () => {
    wrap(
      <JobAuditabilityPanel
        inventoryId="inv1"
        aisleId="a1"
        jobId="j1"
        auditability={fullView({
          metadata_sources: {
            job_row: true,
            result_json: true,
            aisle_join: true,
            inventory_join: true,
            hybrid_report: false,
            execution_log: false,
            run_audit_snapshot: false,
          },
          missing_metadata: ['hybrid_report', 'execution_log'],
        })}
      />
    );
    expect(screen.getByText('Metadata faltante')).toBeInTheDocument();
    expect(screen.getByText('hybrid_report')).toBeInTheDocument();
    expect(screen.getByText('execution_log')).toBeInTheDocument();
  });

  it('shows No informado for null fallback and null inventory visual refs', () => {
    wrap(
      <JobAuditabilityPanel
        inventoryId="inv1"
        aisleId="a1"
        jobId="j1"
        auditability={fullView({
          supplier_prompt_fallback_used: null,
          inventory_visual_references_used: null,
        })}
      />
    );
    const unknownLabels = screen.getAllByText('No informado');
    expect(unknownLabels.length).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText(/no existe una señal confiable para este campo en los artifacts actuales/i)
    ).toBeInTheDocument();
  });

  it('shows loading copy while query is pending', () => {
    vi.spyOn(client, 'getJobAuditability').mockImplementation(() => new Promise(() => {}));
    wrap(<JobAuditabilityPanel inventoryId="inv1" aisleId="a1" jobId="j1" active />);
    expect(screen.getByText(/cargando auditabilidad/i)).toBeInTheDocument();
  });

  it('does not render a prompt_text field', () => {
    wrap(
      <JobAuditabilityPanel
        inventoryId="inv1"
        aisleId="a1"
        jobId="j1"
        auditability={fullView()}
      />
    );
    expect(screen.queryByText(/prompt_text/i)).not.toBeInTheDocument();
  });

  it('shows cost empty state when cost_snapshot is absent', () => {
    wrap(
      <JobAuditabilityPanel
        inventoryId="inv1"
        aisleId="a1"
        jobId="j1"
        auditability={fullView({ cost_snapshot: null })}
      />
    );
    expect(screen.getByTestId('job-auditability-cost')).toBeInTheDocument();
    expect(screen.getByText(/No hay información de costo registrada para esta ejecución/i)).toBeInTheDocument();
  });

  it('renders cost snapshot provider, pricing source, and notes when present', () => {
    wrap(
      <JobAuditabilityPanel
        inventoryId="inv1"
        aisleId="a1"
        jobId="j1"
        auditability={fullView({ cost_snapshot: sampleCostSnapshot() })}
      />
    );
    expect(screen.getByText('Costo del procesamiento')).toBeInTheDocument();
    expect(screen.getByText('gemini-audit-cost')).toBeInTheDocument();
    expect(screen.getByText('catalog_test')).toBeInTheDocument();
    expect(screen.getByText('nota-de-prueba')).toBeInTheDocument();
  });
});
