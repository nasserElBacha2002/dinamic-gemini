/**
 * Sprint 4.2 — Review Queue: global operational workspace for review work across inventories.
 *
 * API lists positions with `needs_review` by default; filters (e.g. status, traceability) narrow that
 * dataset so operators can focus on pending or problematic rows without leaving this screen.
 * Contract: GET /api/v3/review-queue/positions.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import type { ReviewQueueListQuery } from '../api/client';
import type { ReviewQueueItem } from '../api/types';
import { PageHeader } from '../components/shell';
import {
  ErrorAlert,
  FilterToolbar,
  LoadingBlock,
  SectionCard,
  TableSearchField,
  type DataTableSortDirection,
} from '../components/ui';
import { DEFAULT_LIST_PAGE_SIZE, TABLE_SERVER_SEARCH_DEBOUNCE_MS } from '../constants/dataTable';
import ReviewQueueKpiCards from '../features/reviewQueue/components/ReviewQueueKpiCards';
import QuickReviewDrawer from '../features/reviewQueue/components/QuickReviewDrawer';
import {
  reviewQueueItemToContext,
  type OpenReviewDrawerPayload,
  type QuickReviewContext,
} from '../features/reviewQueue/quickReviewContext';
import ReviewQueueTable from '../features/reviewQueue/components/ReviewQueueTable';
import { useAislesList, useDebouncedSearchInput, useInventoriesList, useReviewQueue } from '../hooks';
import { getVisibleErrorMessage } from '../utils/apiErrors';
function parseOptional01(raw: string): number | null {
  const t = raw.trim();
  if (t === '') return null;
  const n = Number(t);
  if (Number.isNaN(n) || n < 0 || n > 1) return null;
  return n;
}

export default function ReviewQueuePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [inventoryId, setInventoryId] = useState('');
  const [aisleId, setAisleId] = useState('');
  const [positionStatus, setPositionStatus] = useState('');
  const [minConfidenceStr, setMinConfidenceStr] = useState('');
  const [maxConfidenceStr, setMaxConfidenceStr] = useState('');
  const [traceability, setTraceability] = useState('');
  const [hasEvidence, setHasEvidence] = useState('');
  const [qtyZero, setQtyZero] = useState('');
  const skuSearch = useDebouncedSearchInput(TABLE_SERVER_SEARCH_DEBOUNCE_MS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_LIST_PAGE_SIZE);
  const [apiSortBy, setApiSortBy] = useState<'priority' | 'updated_at' | 'confidence' | 'created_at'>(
    'priority'
  );
  const [apiSortDir, setApiSortDir] = useState<DataTableSortDirection>('desc');
  const [activeSortColumnId, setActiveSortColumnId] = useState<string>('priority');
  const [reviewDrawerContext, setReviewDrawerContext] = useState<QuickReviewContext | null>(null);
  const consumedRedirectKey = useRef<string | null>(null);

  const inventoriesQuery = useInventoriesList({ page: 1, page_size: 200, sort_by: 'name', sort_dir: 'asc' });
  const aislesQuery = useAislesList(inventoryId || undefined, { enabled: Boolean(inventoryId) });

  const minConfParsedRQ = parseOptional01(minConfidenceStr);
  const maxConfParsedRQ = parseOptional01(maxConfidenceStr);
  const minConfidenceFieldError =
    minConfidenceStr.trim() !== '' && minConfParsedRQ === null ? t('results.min_confidence_help') : '';
  const maxConfidenceFieldError =
    maxConfidenceStr.trim() !== '' && maxConfParsedRQ === null ? t('results.min_confidence_help') : '';
  const confidenceRangeError =
    minConfParsedRQ != null && maxConfParsedRQ != null && minConfParsedRQ > maxConfParsedRQ
      ? t('results.confidence_range_error')
      : '';
  const confidenceFiltersInvalid =
    minConfidenceFieldError !== '' || maxConfidenceFieldError !== '' || confidenceRangeError !== '';

  const listQuery = useMemo((): ReviewQueueListQuery => {
    const minC = confidenceFiltersInvalid ? null : minConfParsedRQ;
    const maxC = confidenceFiltersInvalid ? null : maxConfParsedRQ;
    let hasEv: boolean | null = null;
    if (hasEvidence === 'yes') hasEv = true;
    if (hasEvidence === 'no') hasEv = false;
    let qz: boolean | null = null;
    if (qtyZero === 'yes') qz = true;
    if (qtyZero === 'no') qz = false;
    return {
      inventory_id: inventoryId.trim() || null,
      aisle_id: aisleId.trim() || null,
      min_confidence: minC,
      max_confidence: maxC,
      traceability: traceability.trim() || null,
      has_evidence: hasEv,
      qty_zero: qz,
      sku_contains: skuSearch.applied || null,
      position_status: positionStatus.trim() || null,
      sort_by: apiSortBy,
      sort_dir: apiSortDir,
      page,
      page_size: pageSize,
    };
  }, [
    inventoryId,
    aisleId,
    confidenceFiltersInvalid,
    minConfParsedRQ,
    maxConfParsedRQ,
    traceability,
    hasEvidence,
    qtyZero,
    skuSearch.applied,
    positionStatus,
    apiSortBy,
    apiSortDir,
    page,
    pageSize,
  ]);

  const queueQuery = useReviewQueue(listQuery);
  const totalItems = queueQuery.data?.total_items ?? 0;
  const maxPage = Math.max(1, Math.ceil(Math.max(totalItems, 1) / pageSize));
  const effectivePage = Math.min(page, maxPage);

  const handleResetFilters = useCallback(() => {
    setInventoryId('');
    setAisleId('');
    setPositionStatus('');
    setMinConfidenceStr('');
    setMaxConfidenceStr('');
    setTraceability('');
    setHasEvidence('');
    setQtyZero('');
    skuSearch.setInput('');
    setPage(1);
    setApiSortBy('priority');
    setApiSortDir('desc');
    setActiveSortColumnId('priority');
  }, [skuSearch]);


  const resetDisabled =
    inventoryId === '' &&
    aisleId === '' &&
    positionStatus === '' &&
    minConfidenceStr === '' &&
    maxConfidenceStr === '' &&
    traceability === '' &&
    hasEvidence === '' &&
    qtyZero === '' &&
    skuSearch.input === '' &&
    apiSortBy === 'priority' &&
    apiSortDir === 'desc' &&
    activeSortColumnId === 'priority' &&
    page === 1;

  const errorMessage = queueQuery.isError && queueQuery.error
    ? getVisibleErrorMessage(queueQuery.error, 'reviewQueue')
    : null;

  const summary = queueQuery.data?.summary;
  const items = useMemo(() => queueQuery.data?.items ?? [], [queueQuery.data?.items]);

  const openReviewDrawer = useCallback(
    (item: ReviewQueueItem) => {
      setReviewDrawerContext(reviewQueueItemToContext(item, items.map((i) => i.position.id)));
    },
    [items]
  );

  useEffect(() => {
    const raw = location.state as { openReviewDrawer?: OpenReviewDrawerPayload } | null;
    const p = raw?.openReviewDrawer;
    if (!p || p.kind !== 'queue') return;
    if (
      !p.inventoryId?.trim() ||
      !p.aisleId?.trim() ||
      !p.positionId?.trim() ||
      !p.inventoryName?.trim() ||
      !p.aisleCode?.trim() ||
      !Array.isArray(p.resultIds) ||
      p.resultIds.length === 0
    ) {
      return;
    }
    const key = `${p.positionId}-${p.inventoryId}-${p.aisleId}`;
    if (consumedRedirectKey.current === key) return;
    consumedRedirectKey.current = key;
    setInventoryId(p.inventoryId);
    setAisleId(p.aisleId);
    setReviewDrawerContext({
      inventoryId: p.inventoryId,
      inventoryName: p.inventoryName,
      aisleCode: p.aisleCode,
      aisleId: p.aisleId,
      positionId: p.positionId,
      resultIds: p.resultIds,
      returnTo: 'review_queue',
      jobId: p.jobId,
    });
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: {} });
  }, [location.state, location.pathname, location.search, navigate]);

  return (
    <Box
      sx={{
        width: '100%',
        minWidth: 0,
        maxWidth: '100%',
        overflowX: 'hidden',
        boxSizing: 'border-box',
      }}
    >
      <PageHeader
        a11yTitle={t('routes.review_queue.title')}
        actions={
          <Button size="small" variant="outlined" onClick={() => queueQuery.refetch()} disabled={queueQuery.isFetching}>
            {t('common.refresh')}
          </Button>
        }
      />

      {errorMessage ? (
        <ErrorAlert error={queueQuery.error} context="reviewQueue" onRetry={() => queueQuery.refetch()} />
      ) : null}

      {queueQuery.isLoading && !queueQuery.data ? (
        <LoadingBlock
          message={t('results.loading_workload')}
          py={2}
          sx={{ mb: 2, justifyContent: 'flex-start' }}
        />
      ) : summary ? (
        <ReviewQueueKpiCards summary={summary} />
      ) : null}

      <FilterToolbar onReset={handleResetFilters} resetDisabled={resetDisabled}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 1.5,
            width: '100%',
            flex: '1 1 auto',
            minWidth: 0,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 1.5,
              rowGap: 1.25,
            }}
          >
            <Typography variant="caption" color="text.secondary" sx={{ width: '100%', lineHeight: 1.2 }}>
              {t('review_queue.filter_scope')}
            </Typography>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id="rq-inv-label">{t('common.inventory')}</InputLabel>
              <Select
                labelId="rq-inv-label"
                label={t('common.inventory')}
                value={inventoryId}
                onChange={(e) => {
                  setInventoryId(String(e.target.value));
                  setAisleId('');
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>{t('results.filters.all')}</em>
                </MenuItem>
                {(inventoriesQuery.data?.items ?? []).map((inv) => (
                  <MenuItem key={inv.id} value={inv.id}>
                    {inv.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 140 }} disabled={!inventoryId}>
              <InputLabel id="rq-aisle-label">{t('common.aisle')}</InputLabel>
              <Select
                labelId="rq-aisle-label"
                label={t('common.aisle')}
                value={aisleId}
                onChange={(e) => {
                  setAisleId(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>{t('results.filters.all')}</em>
                </MenuItem>
                {(aislesQuery.data?.items ?? []).map((a) => (
                  <MenuItem key={a.id} value={a.id}>
                    {a.code}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel id="rq-status-label">{t('common.status')}</InputLabel>
              <Select
                labelId="rq-status-label"
                label={t('common.status')}
                value={positionStatus}
                onChange={(e) => {
                  setPositionStatus(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>{t('results.filters.all')}</em>
                </MenuItem>
                <MenuItem value="detected">{t('results.status_menu_detected')}</MenuItem>
                <MenuItem value="confirmed">{t('results.status_menu_confirmed')}</MenuItem>
                <MenuItem value="reviewed">{t('results.status_menu_reviewed')}</MenuItem>
                <MenuItem value="corrected">{t('results.status_menu_corrected')}</MenuItem>
                <MenuItem value="deleted">{t('results.status_menu_deleted')}</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 1.5,
              rowGap: 1.25,
              pt: 0.5,
              borderTop: 1,
              borderColor: 'divider',
            }}
          >
            <Typography variant="caption" color="text.secondary" sx={{ width: '100%', lineHeight: 1.2 }}>
              {t('review_queue.filter_quality_sku')}
            </Typography>
            <TextField
              size="small"
              label={t('results.min_confidence')}
              placeholder={t('review_queue.placeholder_confidence')}
              value={minConfidenceStr}
              onChange={(e) => {
                setMinConfidenceStr(e.target.value);
                setPage(1);
              }}
              sx={{ width: 140 }}
              inputProps={{ inputMode: 'decimal' }}
              error={Boolean(minConfidenceFieldError || confidenceRangeError)}
              helperText={
                minConfidenceFieldError || (confidenceRangeError ? t('results.cannot_exceed_max') : '') || ' '
              }
            />
            <TextField
              size="small"
              label={t('results.max_confidence')}
              placeholder={t('review_queue.placeholder_confidence')}
              value={maxConfidenceStr}
              onChange={(e) => {
                setMaxConfidenceStr(e.target.value);
                setPage(1);
              }}
              sx={{ width: 140 }}
              inputProps={{ inputMode: 'decimal' }}
              error={Boolean(maxConfidenceFieldError || confidenceRangeError)}
              helperText={
                maxConfidenceFieldError || (confidenceRangeError ? t('results.must_be_gte_min') : '') || ' '
              }
            />

            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel id="rq-tr-label">{t('common.traceability')}</InputLabel>
              <Select
                labelId="rq-tr-label"
                label={t('common.traceability')}
                value={traceability}
                onChange={(e) => {
                  setTraceability(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>{t('results.filters.all')}</em>
                </MenuItem>
                <MenuItem value="valid">{t('traceability.valid')}</MenuItem>
                <MenuItem value="missing">{t('traceability.missing')}</MenuItem>
                <MenuItem value="invalid">{t('traceability.invalid')}</MenuItem>
                <MenuItem value="unvalidated">{t('traceability.unvalidated')}</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel id="rq-ev-label">{t('common.evidence')}</InputLabel>
              <Select
                labelId="rq-ev-label"
                label={t('common.evidence')}
                value={hasEvidence}
                onChange={(e) => {
                  setHasEvidence(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>{t('results.filters.all')}</em>
                </MenuItem>
                <MenuItem value="yes">{t('common.present')}</MenuItem>
                <MenuItem value="no">{t('traceability.missing')}</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel id="rq-qz-label">{t('results.qty_zero')}</InputLabel>
              <Select
                labelId="rq-qz-label"
                label={t('results.qty_zero')}
                value={qtyZero}
                onChange={(e) => {
                  setQtyZero(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>{t('results.filters.all')}</em>
                </MenuItem>
                <MenuItem value="yes">{t('common.yes')}</MenuItem>
                <MenuItem value="no">{t('common.no')}</MenuItem>
              </Select>
            </FormControl>

            <TableSearchField
              label={t('results.search_sku')}
              placeholder={t('common.contains_placeholder')}
              value={skuSearch.input}
              onChange={(v) => {
                skuSearch.setInput(v);
                setPage(1);
              }}
              data-testid="review-queue-sku-search"
            />
          </Box>
        </Box>
      </FilterToolbar>

      <SectionCard
        title={t('results.prioritized_results')}
        subtitle={
          activeSortColumnId === 'priority'
            ? t('results.sort_priority_default')
            : activeSortColumnId === 'confidence'
              ? t('results.sort_confidence', {
                  order:
                    apiSortDir === 'desc'
                      ? t('results.sort_confidence_high_low')
                      : t('results.sort_confidence_low_high'),
                })
              : t('results.sort_updated', {
                  order:
                    apiSortDir === 'desc'
                      ? t('results.sort_updated_newest')
                      : t('results.sort_updated_oldest'),
                })
        }
      >
        <Box sx={{ overflow: 'auto' }}>
          <ReviewQueueTable
            rows={items}
            loading={queueQuery.isLoading}
            sort={{
              sortBy: activeSortColumnId,
              sortDir: apiSortDir,
              onSortChange: (sortBy, sortDir) => {
                setActiveSortColumnId(sortBy);
                setPage(1);
                if (sortBy === 'priority') {
                  setApiSortBy('priority');
                  setApiSortDir('desc');
                  return;
                }
                if (sortBy === 'confidence') {
                  setApiSortBy('confidence');
                  setApiSortDir(sortDir);
                  return;
                }
                if (sortBy === 'updated_at') {
                  setApiSortBy('updated_at');
                  setApiSortDir(sortDir);
                }
              },
            }}
            pagination={{
              page: effectivePage,
              pageSize,
              totalItems,
              onPageChange: setPage,
              onPageSizeChange: setPageSize,
            }}
            onOpenReview={openReviewDrawer}
          />
        </Box>
      </SectionCard>

      <QuickReviewDrawer
        open={Boolean(reviewDrawerContext)}
        context={reviewDrawerContext}
        onClose={() => setReviewDrawerContext(null)}
      />
    </Box>
  );
}
