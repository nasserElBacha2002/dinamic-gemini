/**
 * Analytics — benchmark compare (read-only two-run diff). Query: aisleId, jobAId, jobBId.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
} from '@mui/material';
import { PageHeader } from '../../components/shell';
import { useInventoryDetail, useAisleBenchmarkCompare, useAisleJobsList, useAislesList } from '../../hooks';
import { downloadAisleBenchmarkExportCsv } from '../../api/client';
import { getVisibleErrorMessage } from '../../utils/apiErrors';
import { useErrorSnackbar } from '../../components/ui';
import {
  ROUTE_HOME,
  pathToAislePositions,
  pathToInventory,
  pathToInventoryAnalyticsCompareMany,
} from '../../constants/appRoutes';
import { formatSignedDurationHuman } from '../../utils/benchmarkExecutionTime';
import {
  buildCompareRunsDefaultDraftJobs,
  buildCompareRunsDraftSourceKey,
  buildCompareRunsTitleSuffix,
  computeBenchmarkWallClockDelta,
} from '../../features/analytics/adapters/compareRunsViewModel';
import CompareErrorState from '../../features/analytics/components/compare/CompareErrorState';
import CompareDiffTable from '../../features/analytics/components/compare/CompareDiffTable';
import CompareExecutionDeltaPanel from '../../features/analytics/components/compare/CompareExecutionDeltaPanel';
import CompareLoadingState from '../../features/analytics/components/compare/CompareLoadingState';
import CompareNotice from '../../features/analytics/components/compare/CompareNotice';
import CompareRunJobPickerSection from '../../features/analytics/components/compare/CompareRunJobPickerSection';
import CompareScopeContextCard from '../../features/analytics/components/compare/CompareScopeContextCard';
import CompareScopeSelector from '../../features/analytics/components/compare/CompareScopeSelector';
import CompareSummaryCards from '../../features/analytics/components/compare/CompareSummaryCards';

export default function CompareRunsPage() {
  const { t } = useTranslation();
  const { inventoryId } = useParams<{ inventoryId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { showErrorSnackbar } = useErrorSnackbar();

  const aisleId = searchParams.get('aisleId')?.trim() || '';
  const jobAId = searchParams.get('jobAId')?.trim() || '';
  const jobBId = searchParams.get('jobBId')?.trim() || '';

  const [draftOverride, setDraftOverride] = useState<{
    sourceKey: string;
    jobA: string;
    jobB: string;
  } | null>(null);

  const inventoryQuery = useInventoryDetail(inventoryId);
  const aislesQuery = useAislesList(inventoryId, {
    enabled: Boolean(inventoryId && inventoryQuery.data),
  });

  const compareQueryEnabled = Boolean(
    (inventoryId ?? '').trim() &&
      aisleId &&
      jobAId &&
      jobBId &&
      jobAId !== jobBId
  );
  const compareQuery = useAisleBenchmarkCompare(
    inventoryId,
    aisleId || undefined,
    jobAId,
    jobBId,
    { enabled: compareQueryEnabled }
  );
  const jobsQuery = useAisleJobsList(inventoryId, aisleId || undefined, {
    enabled: Boolean(inventoryId && aisleId && inventoryQuery.data),
    limit: 200,
  });

  const inventory = inventoryQuery.data;
  const aislesItems = aislesQuery.data?.items ?? [];
  const aisle = aislesItems.find((a) => a.id === aisleId);
  const jobs = useMemo(() => jobsQuery.data?.jobs ?? [], [jobsQuery.data?.jobs]);
  /** Avoid MUI out-of-range Select when URL aisle is ahead of the aisles list query. */
  const aisleSelectValue =
    aisleId && aislesQuery.isFetched && aislesItems.some((a) => a.id === aisleId) ? aisleId : '';

  /** Avoid repeated replace navigations when inventory refetches but stays non-test. */
  const nonTestRedirectInventoryRef = useRef<string | null>(null);

  useEffect(() => {
    if (!inventoryId) return;
    if (!inventoryQuery.isSuccess) return;
    if (!inventory) return;
    if (inventory.processing_mode === 'test') return;
    if (nonTestRedirectInventoryRef.current === inventoryId) return;
    nonTestRedirectInventoryRef.current = inventoryId;
    navigate(pathToInventory(inventoryId), { replace: true });
  }, [inventory, inventoryId, inventoryQuery.isSuccess, navigate]);

  const draftSourceKey = buildCompareRunsDraftSourceKey(aisleId, jobAId, jobBId);
  const defaultDraftJobs = useMemo(() => {
    return buildCompareRunsDefaultDraftJobs(jobAId, jobBId, jobs);
  }, [jobAId, jobBId, jobs]);
  const draftJobA =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.jobA : defaultDraftJobs.jobA;
  const draftJobB =
    draftOverride?.sourceKey === draftSourceKey ? draftOverride.jobB : defaultDraftJobs.jobB;

  const applyAisleToUrl = useCallback(
    (nextAisleId: string) => {
      setSearchParams((prev) => {
        const p = new URLSearchParams(prev);
        if (nextAisleId) {
          p.set('aisleId', nextAisleId);
        } else {
          p.delete('aisleId');
        }
        p.delete('jobAId');
        p.delete('jobBId');
        return p;
      });
    },
    [setSearchParams]
  );

  const applyJobsToUrl = useCallback(() => {
    if (!draftJobA || !draftJobB || draftJobA === draftJobB) return;
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev);
      p.set('jobAId', draftJobA);
      p.set('jobBId', draftJobB);
      return p;
    });
  }, [draftJobA, draftJobB, setSearchParams]);

  const titleSuffix = useMemo(() => {
    return buildCompareRunsTitleSuffix(jobAId, jobBId);
  }, [jobAId, jobBId]);

  const benchmarkWallClockDelta = useMemo(() => {
    return computeBenchmarkWallClockDelta(compareQuery.data);
  }, [compareQuery.data]);

  if (!inventoryId) {
    return <Alert severity="warning">{t('compare.missing_inventory')}</Alert>;
  }

  const breadcrumbs = [
    { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
    ...(inventory ? [{ label: inventory.name, to: pathToInventory(inventoryId) }] : []),
    { label: t('analytics.compare_runs_breadcrumb') },
  ];

  const compareErrorMessage =
    compareQuery.isError && compareQuery.error
      ? getVisibleErrorMessage(compareQuery.error, 'analytics')
      : null;

  const backHref =
    aisleId && inventoryId ? pathToAislePositions(inventoryId, aisleId) : pathToInventory(inventoryId);

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={t('analytics.compare_runs_page_title')}
        subtitle={t('compare.title_with_ids', {
          suffix: titleSuffix.trim() ? ` ${titleSuffix.trim()}` : '',
        })}
        actions={
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button size="small" variant="outlined" onClick={() => navigate(pathToInventoryAnalyticsCompareMany(inventoryId))}>
              {t('compare_many.open_compare_many')}
            </Button>
            <Button size="small" variant="outlined" onClick={() => navigate(backHref)}>
              {aisleId ? t('compare.back_to_results') : t('analytics.back_to_inventory')}
            </Button>
          </Box>
        }
      />

      <CompareScopeContextCard
        contextLabel={t('analytics.benchmark_context_label')}
        inventoryLabel={t('analytics.context_inventory_label')}
        inventoryValue={inventory?.name ?? t('common.loading')}
        aisleValue={
          aisleId
            ? t('analytics.context_aisle_label', { code: aisle?.code ?? aisleId.slice(0, 8) })
            : t('analytics.context_aisle_not_selected')
        }
        runsLabel={
          jobAId && jobBId
            ? `${t('analytics.context_runs_label')}: ${jobAId.slice(0, 12)}… ↔ ${jobBId.slice(0, 12)}…`
            : undefined
        }
      />

      <CompareNotice severity="info" sx={{ mb: 2 }} message={t('compare.info_benchmark')} />

      <CompareScopeSelector
        isAisleSelected={Boolean(aisleId)}
        aisles={aislesItems}
        aisleSelectValue={aisleSelectValue}
        onAisleChange={applyAisleToUrl}
        selectAisleTitle={t('analytics.select_aisle_title')}
        aisleLabel={t('common.aisle')}
        placeholderLabel={t('analytics.select_aisle_placeholder')}
        changeAisleLabel={t('analytics.change_aisle')}
      />

      <CompareRunJobPickerSection
        visible={Boolean(aisleId && (!jobAId || !jobBId))}
        jobs={jobs}
        draftJobA={draftJobA}
        draftJobB={draftJobB}
        onDraftJobAChange={(jobA) =>
          setDraftOverride({
            sourceKey: draftSourceKey,
            jobA,
            jobB: draftJobB,
          })
        }
        onDraftJobBChange={(jobB) =>
          setDraftOverride({
            sourceKey: draftSourceKey,
            jobA: draftJobA,
            jobB,
          })
        }
        onApplyJobs={applyJobsToUrl}
        sectionTitle={t('benchmark.compare_two_runs_title')}
        description={t('benchmark.compare_readonly_explain')}
        applyLabel={t('analytics.load_comparison')}
        recentRunsLabel={
          jobs.length
            ? t('compare.recent_runs', {
                ids: jobs.map((j) => j.id.slice(0, 8)).join(', '),
              })
            : undefined
        }
      />

      {aisleId && (!jobAId || !jobBId) && !jobs.length && jobsQuery.isFetched ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('compare.warning_need_jobs')}
        </Alert>
      ) : null}

      {compareQuery.isFetching ? <CompareLoadingState sx={{ mb: 2 }} message={t('compare.loading')} /> : null}
      {compareErrorMessage ? (
        <CompareErrorState sx={{ mb: 2 }} message={compareErrorMessage} />
      ) : null}

      {compareQuery.data ? (
        <Box data-testid="compare-runs-results" sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={async () => {
                try {
                  await downloadAisleBenchmarkExportCsv(inventoryId, aisleId, { jobAId, jobBId });
                } catch (e) {
                  showErrorSnackbar(e, 'analytics');
                }
              }}
            >
              {t('compare.export_csv')}
            </Button>
          </Box>

          {(compareQuery.data.raw_fetch_truncated.job_a || compareQuery.data.raw_fetch_truncated.job_b) && (
            <Alert severity="warning">{t('compare.truncation_warning')}</Alert>
          )}

          <CompareSummaryCards runA={compareQuery.data.run_a} runB={compareQuery.data.run_b} />

          {benchmarkWallClockDelta != null ? (
            <CompareExecutionDeltaPanel
              tone={
                benchmarkWallClockDelta > 0
                  ? 'error.main'
                  : benchmarkWallClockDelta < 0
                    ? 'success.main'
                    : 'text.primary'
              }
              value={t('compare.execution_wall_clock_delta', {
                value: formatSignedDurationHuman(benchmarkWallClockDelta),
              })}
              hint={t('compare.execution_lower_is_better')}
            />
          ) : null}

          <CompareDiffTable
            summary={compareQuery.data.diff_summary}
            rows={compareQuery.data.diff_rows}
            rowsTruncated={compareQuery.data.diff_rows_truncated}
          />
        </Box>
      ) : null}
    </>
  );
}
