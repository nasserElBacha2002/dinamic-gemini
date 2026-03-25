/**
 * Sprint 4.2 — Review Queue: global operational workspace for review work across inventories.
 *
 * API lists positions with `needs_review` by default; filters (e.g. status, traceability) narrow that
 * dataset so operators can focus on pending or problematic rows without leaving this screen.
 * Contract: GET /api/v3/review-queue/positions.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { ApiError, type ReviewQueueItem } from '../api/types';
import { PageHeader } from '../components/shell';
import {
  ErrorAlert,
  FilterToolbar,
  SectionCard,
  type DataTableSortDirection,
} from '../components/ui';
import { DEFAULT_LIST_PAGE_SIZE } from '../constants/dataTable';
import ReviewQueueKpiCards from '../features/reviewQueue/components/ReviewQueueKpiCards';
import QuickReviewDrawer from '../features/reviewQueue/components/QuickReviewDrawer';
import {
  reviewQueueItemToContext,
  type OpenReviewDrawerPayload,
  type QuickReviewContext,
} from '../features/reviewQueue/quickReviewContext';
import ReviewQueueTable from '../features/reviewQueue/components/ReviewQueueTable';
import { useAislesList, useInventoriesList, useReviewQueue } from '../hooks';
import { getApiErrorMessage } from '../utils/apiErrors';
function parseOptional01(raw: string): number | null {
  const t = raw.trim();
  if (t === '') return null;
  const n = Number(t);
  if (Number.isNaN(n) || n < 0 || n > 1) return null;
  return n;
}

export default function ReviewQueuePage() {
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
  const [skuContains, setSkuContains] = useState('');
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

  const listQuery = useMemo((): ReviewQueueListQuery => {
    const minC = parseOptional01(minConfidenceStr);
    const maxC = parseOptional01(maxConfidenceStr);
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
      sku_contains: skuContains.trim() || null,
      position_status: positionStatus.trim() || null,
      sort_by: apiSortBy,
      sort_dir: apiSortDir,
      page,
      page_size: pageSize,
    };
  }, [
    inventoryId,
    aisleId,
    minConfidenceStr,
    maxConfidenceStr,
    traceability,
    hasEvidence,
    qtyZero,
    skuContains,
    positionStatus,
    apiSortBy,
    apiSortDir,
    page,
    pageSize,
  ]);

  const queueQuery = useReviewQueue(listQuery);

  useEffect(() => {
    setAisleId('');
  }, [inventoryId]);

  const handleResetFilters = useCallback(() => {
    setInventoryId('');
    setAisleId('');
    setPositionStatus('');
    setMinConfidenceStr('');
    setMaxConfidenceStr('');
    setTraceability('');
    setHasEvidence('');
    setQtyZero('');
    setSkuContains('');
    setPage(1);
    setApiSortBy('priority');
    setApiSortDir('desc');
    setActiveSortColumnId('priority');
  }, []);

  const resetDisabled =
    inventoryId === '' &&
    aisleId === '' &&
    positionStatus === '' &&
    minConfidenceStr === '' &&
    maxConfidenceStr === '' &&
    traceability === '' &&
    hasEvidence === '' &&
    qtyZero === '' &&
    skuContains === '' &&
    apiSortBy === 'priority' &&
    apiSortDir === 'desc' &&
    activeSortColumnId === 'priority' &&
    page === 1;

  const errorMessage =
    queueQuery.isError && queueQuery.error
      ? queueQuery.error instanceof ApiError
        ? getApiErrorMessage(queueQuery.error, 'Failed to load review queue')
        : String(queueQuery.error)
      : null;

  const summary = queueQuery.data?.summary;
  const items = queueQuery.data?.items ?? [];
  const totalItems = queueQuery.data?.total_items ?? 0;

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
    });
    navigate(location.pathname, { replace: true, state: {} });
  }, [location.state, location.pathname, navigate]);

  useEffect(() => {
    if (totalItems === 0) return;
    const pages = Math.max(1, Math.ceil(totalItems / pageSize));
    if (page > pages) setPage(pages);
  }, [totalItems, pageSize, page]);

  return (
    <>
      <PageHeader
        title="Review Queue"
        subtitle="Cross-inventory operational queue for result review."
        actions={
          <Button size="small" variant="outlined" onClick={() => queueQuery.refetch()} disabled={queueQuery.isFetching}>
            Refresh
          </Button>
        }
      />

      {errorMessage ? (
        <ErrorAlert message={errorMessage} onRetry={() => queueQuery.refetch()} />
      ) : null}

      {queueQuery.isLoading && !queueQuery.data ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Loading workload summary…
        </Typography>
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
              Scope
            </Typography>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id="rq-inv-label">Inventory</InputLabel>
              <Select
                labelId="rq-inv-label"
                label="Inventory"
                value={inventoryId}
                onChange={(e) => {
                  setInventoryId(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>All</em>
                </MenuItem>
                {(inventoriesQuery.data?.items ?? []).map((inv) => (
                  <MenuItem key={inv.id} value={inv.id}>
                    {inv.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 140 }} disabled={!inventoryId}>
              <InputLabel id="rq-aisle-label">Aisle</InputLabel>
              <Select
                labelId="rq-aisle-label"
                label="Aisle"
                value={aisleId}
                onChange={(e) => {
                  setAisleId(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>All</em>
                </MenuItem>
                {(aislesQuery.data?.items ?? []).map((a) => (
                  <MenuItem key={a.id} value={a.id}>
                    {a.code}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel id="rq-status-label">Status</InputLabel>
              <Select
                labelId="rq-status-label"
                label="Status"
                value={positionStatus}
                onChange={(e) => {
                  setPositionStatus(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>All</em>
                </MenuItem>
                <MenuItem value="detected">Pending review (detected)</MenuItem>
                <MenuItem value="confirmed">Confirmed (reviewed/corrected)</MenuItem>
                <MenuItem value="reviewed">Reviewed</MenuItem>
                <MenuItem value="corrected">Corrected</MenuItem>
                <MenuItem value="deleted">Deleted</MenuItem>
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
              Quality &amp; SKU
            </Typography>
            <TextField
              size="small"
              label="Min confidence"
              placeholder="0–1"
              value={minConfidenceStr}
              onChange={(e) => {
                setMinConfidenceStr(e.target.value);
                setPage(1);
              }}
              sx={{ width: 120 }}
              inputProps={{ inputMode: 'decimal' }}
            />
            <TextField
              size="small"
              label="Max confidence"
              placeholder="0–1"
              value={maxConfidenceStr}
              onChange={(e) => {
                setMaxConfidenceStr(e.target.value);
                setPage(1);
              }}
              sx={{ width: 120 }}
              inputProps={{ inputMode: 'decimal' }}
            />

            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel id="rq-tr-label">Traceability</InputLabel>
              <Select
                labelId="rq-tr-label"
                label="Traceability"
                value={traceability}
                onChange={(e) => {
                  setTraceability(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>All</em>
                </MenuItem>
                <MenuItem value="valid">Valid</MenuItem>
                <MenuItem value="missing">Missing</MenuItem>
                <MenuItem value="invalid">Invalid</MenuItem>
                <MenuItem value="unvalidated">Unvalidated</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel id="rq-ev-label">Evidence</InputLabel>
              <Select
                labelId="rq-ev-label"
                label="Evidence"
                value={hasEvidence}
                onChange={(e) => {
                  setHasEvidence(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>All</em>
                </MenuItem>
                <MenuItem value="yes">Present</MenuItem>
                <MenuItem value="no">Missing</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel id="rq-qz-label">Qty zero</InputLabel>
              <Select
                labelId="rq-qz-label"
                label="Qty zero"
                value={qtyZero}
                onChange={(e) => {
                  setQtyZero(String(e.target.value));
                  setPage(1);
                }}
              >
                <MenuItem value="">
                  <em>All</em>
                </MenuItem>
                <MenuItem value="yes">Yes</MenuItem>
                <MenuItem value="no">No</MenuItem>
              </Select>
            </FormControl>

            <TextField
              size="small"
              label="Search SKU"
              placeholder="Contains…"
              value={skuContains}
              onChange={(e) => {
                setSkuContains(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 180, flex: '1 1 180px' }}
            />
          </Box>
        </Box>
      </FilterToolbar>

      <SectionCard
        title="Prioritized results"
        subtitle={
          activeSortColumnId === 'priority'
            ? 'Sorted by priority (P1 first), then newest updated.'
            : activeSortColumnId === 'confidence'
              ? `Sorted by confidence (${apiSortDir === 'desc' ? 'high → low' : 'low → high'}).`
              : `Sorted by updated (${apiSortDir === 'desc' ? 'newest first' : 'oldest first'}).`
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
              page,
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
    </>
  );
}
