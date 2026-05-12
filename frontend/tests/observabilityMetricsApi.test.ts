import { describe, it, expect, vi, afterEach } from 'vitest';
import { V3_API_PREFIX } from '../src/constants/v3ApiPaths';
import {
  buildObservabilityMetricsQueryString,
  getObservabilityMetrics,
  getObservabilityMetricsPath,
} from '../src/api/observabilityApi';
import * as http from '../src/api/http';

describe('observability metrics API', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getObservabilityMetricsPath is under v3 observability', () => {
    expect(getObservabilityMetricsPath()).toBe(`${V3_API_PREFIX}/observability/metrics`);
  });

  it('buildObservabilityMetricsQueryString preserves truthy semantics with trim disabled (whitespace from is emitted)', () => {
    const qs = buildObservabilityMetricsQueryString({ from: '   ' });
    expect(new URL(`http://local${qs}`).searchParams.get('from')).toBe('   ');
  });

  it('buildObservabilityMetricsQueryString omits empty string filters', () => {
    expect(buildObservabilityMetricsQueryString({ from: '', to: undefined })).toBe('');
  });

  it('getObservabilityMetrics sends snake_case query params', async () => {
    const fetchSpy = vi.spyOn(http, 'protectedFetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          range: { from: '2026-01-01T00:00:00Z', to: '2026-01-02T00:00:00Z' },
          filters: {
            client_id: 'c1',
            client_supplier_id: 's1',
            provider_name: 'gemini',
            model_name: 'm1',
          },
          totals: {
            runs_total: 0,
            runs_succeeded: 0,
            runs_failed: 0,
            success_rate: null,
            failure_rate: null,
            fallback_runs: 0,
            missing_prompt_config_runs: 0,
            missing_reference_runs: 0,
            legacy_runs: 0,
          },
          by_client: [],
          by_supplier: [],
          by_provider_model: [],
          data_quality: {
            jobs_with_audit_snapshot: 0,
            jobs_without_audit_snapshot: 0,
            jobs_with_missing_metadata: 0,
            artifact_dependent_jobs: 0,
          },
        }),
        { status: 200 }
      )
    );

    await getObservabilityMetrics({
      from: 'a',
      to: 'b',
      clientId: 'c1',
      clientSupplierId: 's1',
      providerName: 'gemini',
      modelName: 'm1',
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toContain('/observability/metrics?');
    expect(url).toContain('from=a');
    expect(url).toContain('to=b');
    expect(url).toContain('client_id=c1');
    expect(url).toContain('client_supplier_id=s1');
    expect(url).toContain('provider_name=gemini');
    expect(url).toContain('model_name=m1');
  });
});
