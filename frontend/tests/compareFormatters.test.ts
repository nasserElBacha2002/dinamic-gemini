import { describe, expect, it, vi } from 'vitest';
import type { TFunction } from 'i18next';
import { formatCostDisplay, userFacingCaptureNote } from '../src/features/analytics/adapters/compareFormatters';

describe('compareFormatters LLM cost notes', () => {
  const t = vi.fn((key: string, opts?: { detail?: string; dimension?: string }) => {
    if (key === 'compare.llm_cost_note.usage_assumption' && opts?.detail) {
      return `Billing assumption: ${opts.detail}`;
    }
    if (key === 'compare.llm_cost_note.canonical_model_without_catalog_entry') {
      return 'Canonical model has no pricing row';
    }
    if (key === 'compare.llm_cost_display.no_pricing_configured') {
      return 'No pricing configured';
    }
    if (key === 'compare.llm_cost_status.unavailable') {
      return 'Unavailable';
    }
    if (key === 'compare.llm_cost_status.estimated') {
      return 'Estimated';
    }
    if (key.startsWith('compare.llm_cost_status.')) {
      return key;
    }
    return key;
  }) as unknown as TFunction;

  it('formats embedded placeholder assumption via usage_assumption branch', () => {
    const note = 'usage_assumption:embedded_pricing_placeholder_not_finance_approved';
    expect(userFacingCaptureNote(note, t)).toBe(
      'Billing assumption: embedded_pricing_placeholder_not_finance_approved'
    );
    expect(t).toHaveBeenCalledWith('compare.llm_cost_note.usage_assumption', {
      detail: 'embedded_pricing_placeholder_not_finance_approved',
    });
  });

  it('maps canonical_model_without_catalog_entry prefixed notes for compare tooltips', () => {
    const note =
      'canonical_model_without_catalog_entry:provider=openai,model=my-short,canonical_model=gpt-x';
    expect(userFacingCaptureNote(note, t)).toBe('Canonical model has no pricing row');
  });

  it('treats canonical_model_without_catalog_entry like missing pricing for value label', () => {
    const out = formatCostDisplay(
      {
        llm_cost_snapshot: {
          capture_status: 'unavailable',
          capture_notes: [
            'canonical_model_without_catalog_entry:provider=openai,model=a,canonical_model=b',
          ],
          computed_cost: { total_cost_unavailable_reason: 'canonical_model_without_catalog_entry' },
        },
      },
      t
    );
    expect(out.value).toBe('No pricing configured');
  });
});
