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

  it('defaults to requested job and shows all lines only after All jobs in log', async () => {
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

    fireEvent.mouseDown(screen.getByLabelText('Job'));
    const opt = await screen.findByRole('option', { name: /All jobs in log/i });
    fireEvent.click(opt);
    await waitFor(() => {
      expect(screen.getByText('for-b')).toBeInTheDocument();
    });
  });

  it('can isolate a specific non-requested job id from the Job select', async () => {
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
              ts: 't0',
              stage: 'S',
              level: 'info',
              message: 'line-a',
              event_job_id: 'job-a',
              is_requested_job_event: true,
            },
            {
              ts: 't1',
              stage: 'S',
              level: 'info',
              message: 'line-b-only',
              event_job_id: 'job-b',
              is_requested_job_event: false,
            },
          ],
        }}
      />
    );
    expect(screen.queryByText('line-b-only')).not.toBeInTheDocument();

    fireEvent.mouseDown(screen.getByLabelText('Job'));
    fireEvent.click(await screen.findByRole('option', { name: /^job-b$/i }));
    await waitFor(() => {
      expect(screen.getByText('line-b-only')).toBeInTheDocument();
    });
    expect(screen.queryByText('line-a')).not.toBeInTheDocument();
  });

  it('derives attempt options from the current job subset and resets invalid attempt after job changes', async () => {
    render(
      <ExecutionLogPanel
        log={{
          inventory_id: 'i',
          aisle_id: 'a',
          requested_job_id: 'job-a',
          available_job_ids: ['job-a', 'job-b'],
          available_attempts: [1, 2, 3],
          available_execution_ids: [],
          events: [
            {
              ts: 't1',
              stage: 'S',
              level: 'info',
              message: 'a1',
              event_job_id: 'job-a',
              event_attempt: 1,
              is_requested_job_event: true,
            },
            {
              ts: 't2',
              stage: 'S',
              level: 'info',
              message: 'a2',
              event_job_id: 'job-a',
              event_attempt: 2,
              is_requested_job_event: true,
            },
            {
              ts: 't3',
              stage: 'S',
              level: 'info',
              message: 'b3',
              event_job_id: 'job-b',
              event_attempt: 3,
              is_requested_job_event: false,
            },
          ],
        }}
      />
    );

    const attemptCombobox = () =>
      screen.getByRole('combobox', { name: 'Attempt', hidden: true });

    fireEvent.mouseDown(attemptCombobox());
    expect(await screen.findByRole('option', { name: '1' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: '3' })).not.toBeInTheDocument();
    fireEvent.keyDown(attemptCombobox(), { key: 'Escape' });

    fireEvent.mouseDown(attemptCombobox());
    fireEvent.click(screen.getByRole('option', { name: '2' }));

    fireEvent.mouseDown(screen.getByLabelText('Job'));
    fireEvent.click(await screen.findByRole('option', { name: /^job-b$/i }));

    await waitFor(() => {
      expect(screen.getByText('b3')).toBeInTheDocument();
    });
    expect(screen.queryByText('a1')).not.toBeInTheDocument();
    expect(screen.queryByText('a2')).not.toBeInTheDocument();
    // Only one distinct attempt exists for job-b; Attempt filter is disabled as redundant.
    expect(attemptCombobox()).toHaveAttribute('aria-disabled', 'true');
  });

  it('legacy log does not show This job chip when no event_job_id exists', () => {
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
    expect(screen.queryByText('This job')).not.toBeInTheDocument();
  });

  it('shows payload for scalar non-object values', () => {
    render(
      <ExecutionLogPanel
        log={{
          inventory_id: 'i',
          aisle_id: 'a',
          requested_job_id: 'j',
          available_job_ids: ['j'],
          available_attempts: [],
          available_execution_ids: [],
          events: [
            {
              ts: 't1',
              stage: 'S',
              level: 'info',
              message: 'scalar-payload',
              payload: 'note',
              event_job_id: 'j',
              is_requested_job_event: true,
            },
          ],
        }}
      />
    );
    expect(screen.getByText(/"note"/)).toBeInTheDocument();
  });
});
