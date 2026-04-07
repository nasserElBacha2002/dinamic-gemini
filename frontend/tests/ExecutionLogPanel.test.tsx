import '@testing-library/jest-dom/vitest';
import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ExecutionLogPanel from '../src/components/ExecutionLogPanel';

describe('ExecutionLogPanel', () => {
  it('renders operator-friendly Gemini request details above the timeline', () => {
    render(
      <ExecutionLogPanel
        events={[
          {
            ts: '2026-03-31T12:00:00Z',
            stage: 'AnalysisStage',
            level: 'info',
            message: 'Gemini request prepared',
            payload: {
              event_type: 'gemini_request',
              provider: 'gemini',
              prompt_text: 'Exact prompt text sent to Gemini.',
              context_instruction: 'Use inventory references only as comparison context.',
              attachment_summary: {
                primary_evidence_count: 2,
                visual_reference_count: 1,
                total_count: 3,
              },
              primary_evidence_attachments: [
                {
                  role: 'primary_evidence',
                  frame_ref: 'img_001',
                  filename: 'input-01.jpg',
                  mime_type: 'image/jpeg',
                },
              ],
              visual_reference_attachments: [
                {
                  role: 'visual_reference',
                  reference_id: 'ref-1',
                  filename: 'reference-front.jpg',
                  mime_type: 'image/jpeg',
                  resolved: true,
                },
              ],
            },
          },
          {
            ts: '2026-03-31T12:00:01Z',
            stage: 'AnalysisStage',
            level: 'info',
            message: 'Gemini analysis request started',
            payload: { frames_count: 2 },
          },
        ]}
      />,
    );

    expect(screen.getByText('Prompt')).toBeInTheDocument();
    expect(screen.getByText('Exact prompt text sent to Gemini.')).toBeInTheDocument();
    expect(screen.getByText('Reference guidance')).toBeInTheDocument();
    expect(screen.getByText('Use inventory references only as comparison context.')).toBeInTheDocument();
    expect(screen.getByText('Attached files')).toBeInTheDocument();
    expect(screen.getByText(/Primary evidence: 2 \| Reference images: 1 \| Total: 3/i)).toBeInTheDocument();
    expect(screen.getByText('img_001: input-01.jpg (image/jpeg)')).toBeInTheDocument();
    expect(screen.getByText('ref-1: reference-front.jpg (image/jpeg)')).toBeInTheDocument();
    expect(screen.getByText('Gemini analysis request started')).toBeInTheDocument();
    expect(screen.queryByText('Gemini request prepared')).not.toBeInTheDocument();
  });

  it('renders multiple Gemini request sections and keeps long prompts scrollable', () => {
    const longPrompt = `Prompt start\n${'x'.repeat(5000)}`;
    render(
      <ExecutionLogPanel
        events={[
          {
            ts: '2026-03-31T12:00:00Z',
            stage: 'AnalysisStage',
            level: 'info',
            message: 'Gemini request prepared',
            payload: {
              event_type: 'gemini_request',
              prompt_text: longPrompt,
              attachment_summary: {
                primary_evidence_count: 1,
                visual_reference_count: 1,
                total_count: 2,
              },
              primary_evidence_attachments: [{ frame_ref: 'img_001', filename: 'first.jpg' }],
              visual_reference_attachments: [{ reference_id: 'ref-1', filename: 'ref-one.jpg', resolved: true }],
            },
          },
          {
            ts: '2026-03-31T12:00:03Z',
            stage: 'AnalysisStage',
            level: 'info',
            message: 'Gemini request prepared',
            payload: {
              event_type: 'gemini_request',
              prompt_text: 'Retry prompt text',
              attachment_summary: {
                primary_evidence_count: 1,
                visual_reference_count: 1,
                total_count: 2,
              },
              primary_evidence_attachments: [{ frame_ref: 'img_002', filename: 'second.jpg' }],
              visual_reference_attachments: [
                { role: 'visual_reference', reference_id: 'ref-2', filename: 'ref-two.jpg', resolved: false },
              ],
            },
          },
        ]}
      />,
    );

    expect(screen.getByText('Gemini request 1')).toBeInTheDocument();
    expect(screen.getByText('Gemini request 2')).toBeInTheDocument();
    expect(screen.getByText('Retry prompt text')).toBeInTheDocument();
    expect(screen.getByText(/ref-two\.jpg/i)).toBeInTheDocument();
    expect(screen.getByText(/\[not resolved\]/i)).toBeInTheDocument();
    const longPromptNode = screen.getByText((content, element) => {
      return element?.tagName.toLowerCase() === 'pre' && content.includes('Prompt start');
    });
    expect(longPromptNode).toHaveStyle({ maxHeight: '240px', overflow: 'auto' });
  });

  it('with enriched log, defaults to current job and hides other job messages until "all" is selected', async () => {
    render(
      <ExecutionLogPanel
        log={{
          inventory_id: 'i',
          aisle_id: 'a',
          requested_job_id: 'job-a',
          available_job_ids: ['job-a', 'job-b'],
          available_attempts: [1],
          available_execution_ids: [],
          events: [
            {
              ts: '2026-01-01T00:00:00Z',
              stage: 'S',
              level: 'info',
              message: 'for-a',
              event_job_id: 'job-a',
              event_attempt: 1,
              is_requested_job_event: true,
            },
            {
              ts: '2026-01-01T00:00:01Z',
              stage: 'S',
              level: 'info',
              message: 'for-b',
              event_job_id: 'job-b',
              event_attempt: 1,
              is_requested_job_event: false,
            },
          ],
        }}
      />
    );
    expect(screen.getByText('for-a')).toBeInTheDocument();
    expect(screen.queryByText('for-b')).not.toBeInTheDocument();

    fireEvent.mouseDown(screen.getByLabelText('Job context'));
    const opt = await screen.findByRole('option', { name: /All job ids in log/i });
    fireEvent.click(opt);
    await waitFor(() => {
      expect(screen.getByText('for-b')).toBeInTheDocument();
    });
  });

  it('shows legacy note when no event job_id is present', () => {
    render(
      <ExecutionLogPanel
        log={{
          inventory_id: 'i',
          aisle_id: 'a',
          requested_job_id: 'job-x',
          available_job_ids: ['job-x'],
          available_attempts: [],
          available_execution_ids: [],
          events: [
            {
              ts: 't1',
              stage: 'S',
              level: 'info',
              message: 'legacy-line',
              is_requested_job_event: true,
            },
          ],
        }}
      />
    );
    expect(screen.getByText(/Job metadata unavailable/i)).toBeInTheDocument();
    expect(screen.getByText('legacy-line')).toBeInTheDocument();
  });
});
