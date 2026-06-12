/**
 * Job Detail metadata: prefer persisted job.finished_at; when it is inconsistent with
 * started_at / step timestamps or missing, fall back to execution log terminal events.
 */

import type { ExecutionLogEvent } from '../api/types';

function parseTs(iso: string): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? NaN : t;
}

const TERMINAL_LOG_MESSAGES = new Set([
  'job.succeeded',
  'provider_pipeline.completed',
  'analysis.completed',
  'job.failed',
  'job.canceled',
]);

export type JobLikeForFinished = {
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  current_step_started_at?: string | null;
};

/**
 * ISO timestamp for "Finished" in Job Detail, or null if the job is not terminal / no value.
 */
export function resolveDisplayFinishedAt(
  job: JobLikeForFinished,
  logEvents?: ExecutionLogEvent[] | null
): string | null {
  const st = String(job.status || '').toLowerCase();
  const terminal = st === 'succeeded' || st === 'failed' || st === 'canceled';
  if (!terminal) return null;

  const started = job.started_at ? parseTs(job.started_at) : NaN;
  const finished = job.finished_at ? parseTs(job.finished_at) : NaN;
  const stepStarted = job.current_step_started_at ? parseTs(job.current_step_started_at) : NaN;

  const coherent =
    Boolean(job.finished_at) &&
    !Number.isNaN(finished) &&
    (!Number.isNaN(started) ? finished >= started : true) &&
    (!Number.isNaN(stepStarted) ? finished >= stepStarted : true);

  if (coherent) return job.finished_at!;

  if (logEvents?.length) {
    const terminals = logEvents.filter((e) => TERMINAL_LOG_MESSAGES.has(String(e.message || '').trim()));
    const pool = terminals.length > 0 ? terminals : logEvents;
    let best = pool[0]!;
    let bestTs = parseTs(best.ts);
    for (const e of pool) {
      const t = parseTs(e.ts);
      if (!Number.isNaN(t) && (Number.isNaN(bestTs) || t >= bestTs)) {
        best = e;
        bestTs = t;
      }
    }
    return best.ts;
  }

  return job.finished_at ?? null;
}
