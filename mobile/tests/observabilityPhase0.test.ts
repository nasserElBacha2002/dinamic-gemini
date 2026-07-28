import {
  compressionRatio,
  normalizeNetworkType,
  normalizeObservabilityError,
  percentile,
  summarizeMetric,
  sanitizeObservabilityAttributes,
  sanitizeObservabilityEvent,
  NoOpObservabilityReporter,
  SafeObservabilityReporter,
  FlaggedObservabilityReporter,
  buildBaselineReport,
  createMonotonicClock,
  elapsedMs,
} from '../src/observability';
import type { ObservabilityEvent, ObservabilityReporter } from '../src/observability';

describe('observability Phase 0 core', () => {
  describe('clock / duration', () => {
    it('computes elapsed ms from monotonic clock', () => {
      let t = 100;
      const clock = createMonotonicClock(() => t);
      const start = clock.nowMs();
      t = 250.4;
      expect(elapsedMs(clock, start)).toBe(150);
    });
  });

  describe('compressionRatio', () => {
    it('returns null when inputs are missing or invalid', () => {
      expect(compressionRatio(null, 10)).toBeNull();
      expect(compressionRatio(0, 10)).toBeNull();
      expect(compressionRatio(100, null)).toBeNull();
    });

    it('computes prepared/original ratio', () => {
      expect(compressionRatio(1000, 250)).toBe(0.25);
    });
  });

  describe('normalizeNetworkType', () => {
    it('maps known types and offline', () => {
      expect(normalizeNetworkType({ isConnected: false })).toBe('offline');
      expect(normalizeNetworkType({ isConnected: true, type: 'wifi' })).toBe('wifi');
      expect(normalizeNetworkType({ isConnected: true, type: 'cellular' })).toBe('cellular');
      expect(normalizeNetworkType({ isConnected: true, isCellular: true })).toBe('cellular');
      expect(normalizeNetworkType({ isConnected: true, type: 'ethernet' })).toBe('ethernet');
      expect(normalizeNetworkType({ isConnected: true, type: 'vpn' })).toBe('unknown');
    });
  });

  describe('normalizeObservabilityError', () => {
    it('maps prepare/upload/http stages', () => {
      expect(
        normalizeObservabilityError({ stage: 'prepare', message: 'Archivo vacío' }),
      ).toBe('PREPARE_READ_FAILED');
      expect(normalizeObservabilityError({ stage: 'upload', httpStatus: 413 })).toBe(
        'UPLOAD_LIMIT_EXCEEDED',
      );
      expect(normalizeObservabilityError({ stage: 'upload', httpStatus: 503 })).toBe(
        'UPLOAD_HTTP_5XX',
      );
      expect(normalizeObservabilityError({ stage: 'upload', httpStatus: 400 })).toBe(
        'UPLOAD_HTTP_4XX',
      );
      expect(normalizeObservabilityError({ stage: 'process', message: 'fail' })).toBe(
        'PROCESS_REQUEST_FAILED',
      );
    });
  });

  describe('sanitize', () => {
    it('strips sensitive attribute keys', () => {
      const cleaned = sanitizeObservabilityAttributes({
        prepare_ms: 12,
        uri: 'file:///secret.jpg',
        token: 'abc',
        client_file_id: 'cf-1',
      });
      expect(cleaned).toEqual({ prepare_ms: 12, client_file_id: 'cf-1' });
    });

    it('sanitizes full events', () => {
      const event = sanitizeObservabilityEvent({
        name: 'photo.prepare_completed',
        timestamp: '2026-01-01T00:00:00.000Z',
        attributes: { display_name: 'x.jpg', prepare_ms: 5 },
      });
      expect(event.attributes).toEqual({ prepare_ms: 5 });
    });
  });

  describe('reporters', () => {
    it('NoOp never throws and records nothing', () => {
      const reporter = new NoOpObservabilityReporter();
      expect(() =>
        reporter.emit({ name: 'x', timestamp: '2026-01-01T00:00:00.000Z' }),
      ).not.toThrow();
    });

    it('SafeObservabilityReporter swallows inner failures', () => {
      const errors: unknown[] = [];
      const failing: ObservabilityReporter = {
        emit() {
          throw new Error('boom');
        },
      };
      const safe = new SafeObservabilityReporter(failing, (e) => errors.push(e));
      expect(() =>
        safe.emit({
          name: 'photo.upload_completed',
          timestamp: '2026-01-01T00:00:00.000Z',
          attributes: { uri: 'file://x' },
        }),
      ).not.toThrow();
      expect(errors).toHaveLength(1);
    });

    it('FlaggedObservabilityReporter respects kill switch', () => {
      const events: ObservabilityEvent[] = [];
      const inner: ObservabilityReporter = {
        emit(e) {
          events.push(e);
        },
      };
      const flagged = new FlaggedObservabilityReporter(() => false, inner);
      flagged.emit({ name: 'x', timestamp: '2026-01-01T00:00:00.000Z' });
      expect(events).toHaveLength(0);
      const on = new FlaggedObservabilityReporter(() => true, inner);
      on.emit({ name: 'y', timestamp: '2026-01-01T00:00:00.000Z' });
      expect(events).toHaveLength(1);
    });
  });

  describe('baseline percentiles', () => {
    it('computes p50/p95/max/avg', () => {
      const values = [10, 20, 30, 40, 50];
      expect(percentile(values, 50)).toBe(30);
      const summary = summarizeMetric(values);
      expect(summary.count).toBe(5);
      expect(summary.p50).toBe(30);
      expect(summary.max).toBe(50);
    });

    it('builds baseline report from events', () => {
      const report = buildBaselineReport([
        {
          name: 'photo.prepare_completed',
          durationMs: 100,
          attributes: {
            original_bytes: 1000,
            prepared_bytes: 400,
            compression_ratio: 0.4,
            network_type: 'wifi',
          },
        },
        {
          name: 'photo.upload_completed',
          durationMs: 200,
          attributes: { network_type: 'wifi' },
        },
        {
          name: 'session.capture_to_first_server_result',
          durationMs: null,
          attributes: { capture_to_first_server_result_ms: 5000 },
        },
        {
          name: 'session.job_terminal',
          durationMs: null,
          attributes: { capture_to_job_terminal_ms: 9000 },
        },
      ]);
      expect(report.metrics.prepare_ms.count).toBe(1);
      expect(report.metrics.upload_ms.p50).toBe(200);
      expect(report.metrics.compression_ratio.avg).toBe(0.4);
      expect(report.byNetwork.wifi?.upload_ms.count).toBe(1);
    });
  });
});
