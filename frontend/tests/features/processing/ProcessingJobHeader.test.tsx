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
});
