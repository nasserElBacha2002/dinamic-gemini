/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProcessingJobHeader from '../../../src/features/processing/ProcessingJobHeader';
import type { JobSummary } from '../../../src/api/types';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../src/i18n';

function renderHeader(job: JobSummary | null) {
  return render(
    <I18nextProvider i18n={i18n}>
      <ProcessingJobHeader job={job} />
    </I18nextProvider>,
  );
}

describe('ProcessingJobHeader', () => {
  it('renders configured vs executed fallback identities separately', () => {
    const job = {
      id: 'job-1',
      status: 'RUNNING',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      provider_name: 'gemini',
      model_name: 'gemini-3.1-pro-preview',
      prompt_key: 'global_v22',
      identification_execution: {
        external_fallback: {
          fallback_enabled: true,
          fallback_provider: 'claude',
          fallback_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_single_label',
        },
      },
      fallback_progress: { fallback_requested: 1, resolved_external: 1 },
      fallback_asset_summaries: [
        {
          asset_id: 'a1',
          external_provider: 'claude',
          executed_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_single_label',
        },
      ],
    } as unknown as JobSummary;

    renderHeader(job);
    expect(screen.getByTestId('processing-job-fallback-configured').textContent).toContain('claude');
    expect(screen.getByTestId('processing-job-fallback-executed').textContent).toContain('claude');
    expect(screen.getByTestId('processing-job-historical-metadata-warning')).toBeTruthy();
  });

  it('shows not executed when fallback configured but unused', () => {
    const job = {
      id: 'job-2',
      status: 'COMPLETED',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      identification_mode: 'INTERNAL_OCR',
      execution_strategy: 'INTERNAL_OCR',
      identification_execution: {
        external_fallback: {
          fallback_enabled: true,
          fallback_provider: 'claude',
          fallback_model: 'claude-opus-4-7',
          prompt_key: 'external_fallback_single_label',
        },
      },
    } as unknown as JobSummary;

    renderHeader(job);
    expect(screen.getByTestId('processing-job-fallback-executed').textContent).toMatch(/not executed|no ejecutado/i);
  });

  it('renders unambiguous Job / Pasillo / Inventario / Execution labels', () => {
    const job = {
      id: '939ecf64-8598-4694-a552-d15535ab0a45',
      status: 'COMPLETED',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      execution_id: 'dbd9efbf-1111-2222-3333-444444444444',
      identification_mode: 'CODE_SCAN_ONLY',
      execution_strategy: 'CODE_SCAN',
    } as unknown as JobSummary;

    render(
      <I18nextProvider i18n={i18n}>
        <ProcessingJobHeader
          job={job}
          inventoryId="ec321684-aaaa-bbbb-cccc-ddddeeeeffff"
          aisleId="83934f6e-28dc-4bfc-a262-228d710bb37d"
        />
      </I18nextProvider>,
    );

    const identity = screen.getByTestId('processing-job-identity-ids');
    expect(identity.textContent).toMatch(/Job/i);
    expect(identity.textContent).toMatch(/Pasillo|Aisle/i);
    expect(identity.textContent).toMatch(/Inventario|Inventory/i);
    expect(identity.textContent).toMatch(/Execution/i);
    expect(identity.textContent).toContain('939ecf64-8598-4694-a552-d15535ab0a45');
    expect(identity.textContent).toContain('83934f6e-28dc-4bfc-a262-228d710bb37d');
    expect(identity.textContent).toContain('ec321684-aaaa-bbbb-cccc-ddddeeeeffff');
    expect(identity.textContent).toContain('dbd9efbf-1111-2222-3333-444444444444');
    expect(identity.textContent).not.toMatch(/Ejec\.\s/);
  });
});
