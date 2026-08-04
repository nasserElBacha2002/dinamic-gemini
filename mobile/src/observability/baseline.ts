/**
 * Percentile helpers for Phase 0 baseline export (no external deps).
 */

export function percentile(sortedAscending: readonly number[], p: number): number | null {
  if (sortedAscending.length === 0) {
    return null;
  }
  if (p <= 0) {
    return sortedAscending[0]!;
  }
  if (p >= 100) {
    return sortedAscending[sortedAscending.length - 1]!;
  }
  const rank = (p / 100) * (sortedAscending.length - 1);
  const low = Math.floor(rank);
  const high = Math.ceil(rank);
  if (low === high) {
    return sortedAscending[low]!;
  }
  const weight = rank - low;
  return sortedAscending[low]! * (1 - weight) + sortedAscending[high]! * weight;
}

export interface MetricSummary {
  readonly count: number;
  readonly p50: number | null;
  readonly p95: number | null;
  readonly max: number | null;
  readonly avg: number | null;
}

export function summarizeMetric(values: readonly number[]): MetricSummary {
  const clean = values.filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (clean.length === 0) {
    return { count: 0, p50: null, p95: null, max: null, avg: null };
  }
  const sorted = [...clean].sort((a, b) => a - b);
  const sum = sorted.reduce((a, b) => a + b, 0);
  return {
    count: sorted.length,
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    max: sorted[sorted.length - 1]!,
    avg: Math.round((sum / sorted.length) * 100) / 100,
  };
}

export interface BaselineReport {
  readonly generatedAt: string;
  readonly eventCount: number;
  readonly metrics: {
    readonly prepare_ms: MetricSummary;
    readonly upload_ms: MetricSummary;
    readonly original_bytes: MetricSummary;
    readonly prepared_bytes: MetricSummary;
    readonly compression_ratio: MetricSummary;
    readonly capture_to_first_server_result_ms: MetricSummary;
    readonly capture_to_job_terminal_ms: MetricSummary;
    readonly finish_ms: MetricSummary;
    readonly finish_media_store_check_ms: MetricSummary;
    readonly finish_validation_wait_ms: MetricSummary;
  };
  readonly byNetwork: Record<string, { readonly upload_ms: MetricSummary; readonly prepare_ms: MetricSummary }>;
  readonly errorCounts: Record<string, number>;
  readonly finishExtra: {
    readonly new_media_candidates_events: number;
    readonly skipped_full_rescan_events: number;
    readonly orphan_reclaimed: number;
    readonly upload_healed: number;
  };
  readonly notes: readonly string[];
}

export interface ParsedObsEvent {
  readonly name: string;
  readonly durationMs: number | null;
  readonly attributes: Record<string, string | number | boolean | null>;
}

export function buildBaselineReport(
  events: readonly ParsedObsEvent[],
  now: () => Date = () => new Date(),
): BaselineReport {
  const collect = (name: string, attr?: string): number[] => {
    const out: number[] = [];
    for (const e of events) {
      if (e.name !== name) {
        continue;
      }
      if (attr) {
        const v = e.attributes[attr];
        if (typeof v === 'number' && Number.isFinite(v)) {
          out.push(v);
        }
      } else if (e.durationMs != null && Number.isFinite(e.durationMs)) {
        out.push(e.durationMs);
      }
    }
    return out;
  };

  const networks = new Set<string>();
  for (const e of events) {
    const n = e.attributes.network_type;
    if (typeof n === 'string' && n) {
      networks.add(n);
    }
  }

  const byNetwork: BaselineReport['byNetwork'] = {};
  for (const net of networks) {
    const prepare: number[] = [];
    const upload: number[] = [];
    for (const e of events) {
      if (e.attributes.network_type !== net) {
        continue;
      }
      if (e.name === 'photo.prepare_completed' && e.durationMs != null) {
        prepare.push(e.durationMs);
      }
      if (e.name === 'photo.upload_completed' && e.durationMs != null) {
        upload.push(e.durationMs);
      }
    }
    byNetwork[net] = {
      prepare_ms: summarizeMetric(prepare),
      upload_ms: summarizeMetric(upload),
    };
  }

  const errorCounts: Record<string, number> = {};
  for (const e of events) {
    if (!e.name.endsWith('_failed') && e.name !== 'photo.upload_retry' && e.name !== 'job.terminal_failed') {
      continue;
    }
    const code = e.attributes.error_code;
    const key = typeof code === 'string' ? code : e.name;
    errorCounts[key] = (errorCounts[key] ?? 0) + 1;
  }

  const finishExtra = {
    new_media_candidates_events: events.filter((e) => e.name === 'capture.finish_new_media_candidates').length,
    skipped_full_rescan_events: events.filter(
      (e) => e.name === 'capture.finish_scan_completed' && e.attributes.skipped_full_rescan === true,
    ).length,
    orphan_reclaimed: events.filter((e) => e.name === 'upload.orphan_reclaimed').length,
    upload_healed: events.filter((e) => e.name === 'photo.upload_healed').length,
  };

  return {
    generatedAt: now().toISOString(),
    eventCount: events.length,
    metrics: {
      prepare_ms: summarizeMetric(collect('photo.prepare_completed')),
      upload_ms: summarizeMetric(collect('photo.upload_completed')),
      original_bytes: summarizeMetric(collect('photo.prepare_completed', 'original_bytes')),
      prepared_bytes: summarizeMetric(collect('photo.prepare_completed', 'prepared_bytes')),
      compression_ratio: summarizeMetric(collect('photo.prepare_completed', 'compression_ratio')),
      capture_to_first_server_result_ms: summarizeMetric(
        collect('session.capture_to_first_server_result', 'capture_to_first_server_result_ms'),
      ),
      capture_to_job_terminal_ms: summarizeMetric(
        collect('session.job_terminal', 'capture_to_job_terminal_ms'),
      ),
      finish_ms: summarizeMetric(collect('capture.finish_completed')),
      finish_media_store_check_ms: summarizeMetric(collect('capture.finish_media_store_check_completed')),
      finish_validation_wait_ms: summarizeMetric(collect('capture.finish_validation_wait_completed')),
    },
    byNetwork,
    errorCounts,
    finishExtra,
    notes: [
      'Phase 0/1 baseline — finish stage events + upload prepare/upload.',
      'Enable captureFinishInstrumentation (default on).',
      'Device S10+ manual runs should be attached separately when available.',
    ],
  };
}

export function rowsToParsedEvents(
  rows: readonly {
    readonly name: string;
    readonly duration_ms: number | null;
    readonly attributes_json: string;
  }[],
): ParsedObsEvent[] {
  return rows.map((r) => {
    let attributes: Record<string, string | number | boolean | null> = {};
    try {
      const parsed = JSON.parse(r.attributes_json) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        attributes = parsed as Record<string, string | number | boolean | null>;
      }
    } catch {
      attributes = {};
    }
    return {
      name: r.name,
      durationMs: r.duration_ms,
      attributes,
    };
  });
}
