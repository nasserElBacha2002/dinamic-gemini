/**
 * Epic 3.1.B — Job count results page (v1 API).
 * Lists counted items for a job with source image and traceability status.
 */

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
} from '@mui/material';
import type { JobEntityListItem } from '../api/types';
import { ApiError } from '../api/types';
import { getApiErrorMessage } from '../utils/apiErrors';
import { isTraceabilityStatus } from '../utils/traceability';
import { PageLayout, LoadingBlock, EmptyState, ErrorAlert, TraceabilityChip } from '../components/ui';
import { useJobEntities } from '../hooks';

function displayOptional(value: string | null | undefined): string {
  if (value == null || String(value).trim() === '') return '—';
  return String(value).trim();
}

export default function JobEntitiesPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { data, isLoading, isError, error, refetch } = useJobEntities(jobId);
  const entities = data?.entities ?? [];
  const errorMessage =
    isError && error
      ? error instanceof ApiError
        ? getApiErrorMessage(error, 'Failed to load count results')
        : String(error)
      : null;

  const handleBack = () => navigate(-1);

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

      {isLoading && !data ? (
        <LoadingBlock message="Loading count results…" />
      ) : errorMessage ? (
        <ErrorAlert message={errorMessage} onRetry={() => refetch()} />
      ) : entities.length === 0 ? (
        <EmptyState message="No count results for this job yet. Run processing on the aisle, or check back once the job has finished." />
      ) : (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Item</TableCell>
                <TableCell>Pallet</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Count status</TableCell>
                <TableCell>Source image</TableCell>
                <TableCell>Traceability</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entities.map((entity: JobEntityListItem) => (
                <TableRow key={entity.entity_uid}>
                  <TableCell>{displayOptional(entity.entity_uid)}</TableCell>
                  <TableCell>{displayOptional(entity.pallet_id)}</TableCell>
                  <TableCell>{displayOptional(entity.entity_type)}</TableCell>
                  <TableCell>{displayOptional(entity.count_status)}</TableCell>
                  <TableCell>{displayOptional(entity.source_image_id)}</TableCell>
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
