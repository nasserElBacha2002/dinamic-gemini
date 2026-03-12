/**
 * Epic 3.1.B / 3.1.C / Epic 4 / Epic 5 — Job count results page (v1 API).
 * Lists counted items with source image ID, source file (original filename), and traceability status.
 * Epic 5: displays source_image_original_filename as "Source file" (distinct from internal "Source image ID").
 */

import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Link,
  Box,
  Tabs,
  Tab,
} from '@mui/material';
import type { JobEntityListItem, TraceabilitySummary } from '../api/types';
import { ApiError } from '../api/types';
import { TRACEABILITY_STATUSES } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { isTraceabilityStatus } from '../utils/traceability';
import { PageLayout, LoadingBlock, EmptyState, ErrorAlert, TraceabilityChip } from '../components/ui';
import { useJobEntities } from '../hooks';

function displayOptional(value: string | null | undefined): string {
  if (value == null || String(value).trim() === '') return '—';
  return String(value).trim();
}

/** Epic 4: review-oriented display label. Prefers review_display_label; falls back to product_display_label for legacy responses. Normalization (empty/whitespace → —) is done by displayOptional. */
function getEntityDisplayLabel(entity: JobEntityListItem): string | null | undefined {
  return entity.review_display_label ?? entity.product_display_label;
}

const TRACEABILITY_FILTER_ALL = 'all';

/** Epic 3.1.C — Compact summary row when backend provides traceability_summary. */
function TraceabilitySummaryBlock({ summary }: { summary: TraceabilitySummary }) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 2,
        alignItems: 'center',
        mb: 2,
        p: 1.5,
        borderRadius: 1,
        bgcolor: 'action.hover',
      }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ mr: 1 }}>
        Traceability (job total):
      </Typography>
      <Typography component="span" variant="body2" sx={{ fontWeight: 500 }}>
        Total {summary.total_entities}
      </Typography>
      <Typography component="span" variant="body2" color="success.main">
        Valid {summary.valid}
      </Typography>
      <Typography component="span" variant="body2" color="text.secondary">
        Missing {summary.missing}
      </Typography>
      <Typography component="span" variant="body2" color="error.main">
        Invalid {summary.invalid}
      </Typography>
      <Typography component="span" variant="body2" color="info.main">
        Unvalidated {summary.unvalidated}
      </Typography>
    </Box>
  );
}

export default function JobEntitiesPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [traceabilityFilter, setTraceabilityFilter] = useState<string>(TRACEABILITY_FILTER_ALL);

  const traceabilityStatusParam =
    traceabilityFilter === TRACEABILITY_FILTER_ALL
      ? undefined
      : (isTraceabilityStatus(traceabilityFilter) ? traceabilityFilter : undefined);

  const { data, isLoading, isError, error, refetch } = useJobEntities(jobId, {
    traceability_status: traceabilityStatusParam,
  });

  const entities = data?.entities ?? [];
  const traceabilitySummary = data?.traceability_summary ?? undefined;
  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load count results')
        : String(error)
      : null;

  const handleBack = () => navigate(-1);
  const handleFilterChange = useCallback((_e: React.SyntheticEvent, value: string) => {
    setTraceabilityFilter(value);
  }, []);

  if (!jobId?.trim()) {
    return (
      <PageLayout>
        <Typography color="text.secondary">Missing job ID.</Typography>
        <Button sx={{ mt: 2 }} onClick={() => navigate('/')}>
          Back to inventories
        </Button>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <Typography component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, flexWrap: 'wrap' }}>
        <Button onClick={handleBack}>← Back</Button>
        <Link component="button" variant="body2" onClick={() => navigate('/')} sx={{ cursor: 'pointer' }}>
          Inventories
        </Link>
      </Typography>

      <Typography variant="h6" sx={{ mb: 2 }}>
        Count results — Job {jobId.slice(0, 8)}{jobId.length > 8 ? '…' : ''}
      </Typography>

      {traceabilitySummary != null && (
        <TraceabilitySummaryBlock summary={traceabilitySummary} />
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={traceabilityFilter} onChange={handleFilterChange} variant="scrollable" scrollButtons="auto">
          <Tab label="All" value={TRACEABILITY_FILTER_ALL} />
          {(TRACEABILITY_STATUSES as readonly string[]).map((status) => (
            <Tab key={status} label={status.charAt(0).toUpperCase() + status.slice(1)} value={status} />
          ))}
        </Tabs>
      </Box>

      {isLoading && !data ? (
        <LoadingBlock message="Loading count results…" />
      ) : errorMessage ? (
        <ErrorAlert message={errorMessage} onRetry={() => refetch()} />
      ) : entities.length === 0 ? (
        <EmptyState
          message={
            traceabilityStatusParam
              ? 'No entities match the selected traceability filter.'
              : 'No count results for this job yet. Run processing on the aisle, or check back once the job has finished.'
          }
        />
      ) : (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Item</TableCell>
                <TableCell>Review label</TableCell>
                <TableCell>Pallet</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Count status</TableCell>
                <TableCell>Source image ID</TableCell>
                <TableCell>Source file</TableCell>
                <TableCell>Traceability</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entities.map((entity: JobEntityListItem) => (
                <TableRow key={entity.entity_uid}>
                  <TableCell>{displayOptional(entity.entity_uid)}</TableCell>
                  <TableCell>{displayOptional(getEntityDisplayLabel(entity))}</TableCell>
                  <TableCell>{displayOptional(entity.pallet_id)}</TableCell>
                  <TableCell>{displayOptional(entity.entity_type)}</TableCell>
                  <TableCell>{displayOptional(entity.count_status)}</TableCell>
                  <TableCell>{displayOptional(entity.source_image_id)}</TableCell>
                  <TableCell>{displayOptional(entity.source_image_original_filename)}</TableCell>
                  <TableCell>
                    {isTraceabilityStatus(entity.traceability_status) ? (
                      <TraceabilityChip
                        status={entity.traceability_status}
                        tooltip={entity.traceability_warning ?? undefined}
                      />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </PageLayout>
  );
}
