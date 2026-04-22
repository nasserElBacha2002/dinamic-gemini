import ArrowBackOutlinedIcon from '@mui/icons-material/ArrowBackOutlined';
import { Button, Stack } from '@mui/material';
import { useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { PageHeader } from '../../../components/shell';
import { ErrorAlert, SectionCard } from '../../../components/ui';
import { ROUTE_INGESTION_SESSIONS } from '../../../constants/appRoutes';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import ImportSessionDetail from '../components/ImportSessionDetail';
import { useCaptureSessionDetail, useCloseCaptureSession } from '../hooks/useCaptureSessions';
import type { CaptureSessionStatus } from '../../../types/captureSession';

function computeGuards(status: CaptureSessionStatus, hasItems: boolean, closedAt: string | null | undefined) {
  const isClosed = Boolean(closedAt);
  const canUpload = (status === 'draft' || status === 'importing') && !isClosed;
  const canClose = (status === 'draft' || status === 'importing' || status === 'ready_for_review') && hasItems;
  return { canUpload, canClose };
}

export default function IngestionSessionDetailPage() {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();
  const [searchParams] = useSearchParams();
  const inventoryId = searchParams.get('inventoryId') ?? '';
  const aisleId = searchParams.get('aisleId') ?? '';

  const detailQuery = useCaptureSessionDetail(inventoryId || undefined, sessionId || undefined, {
    enabled: Boolean(inventoryId && sessionId),
  });
  const closeMutation = useCloseCaptureSession();

  const errorMessage = useMemo(() => {
    const err = detailQuery.error || closeMutation.error;
    if (!err) return null;
    return resolveApiErrorMessage(err, 'errors.request_failed');
  }, [closeMutation.error, detailQuery.error]);

  if (!inventoryId || !aisleId || !sessionId) {
    return (
      <ErrorAlert
        message="Missing inventoryId/aisleId/sessionId in route parameters."
        onRetry={() => navigate(ROUTE_INGESTION_SESSIONS)}
      />
    );
  }

  return (
    <Stack spacing={2}>
      <PageHeader
        title="Import Session Detail"
        actions={
          <Button
            variant="outlined"
            startIcon={<ArrowBackOutlinedIcon />}
            onClick={() => navigate(ROUTE_INGESTION_SESSIONS)}
          >
            Back to sessions
          </Button>
        }
      />

      {errorMessage ? <ErrorAlert message={errorMessage} onRetry={() => detailQuery.refetch()} /> : null}

      <SectionCard title="Session">
        {detailQuery.data ? (
          <ImportSessionDetail
            detail={detailQuery.data}
            onRefresh={() => {
              void detailQuery.refetch();
            }}
            onCloseSession={() => {
              void closeMutation.mutateAsync({ inventoryId, aisleId, sessionId });
            }}
            closing={closeMutation.isPending}
            {...computeGuards(
              detailQuery.data.session.status,
              detailQuery.data.items.length > 0,
              detailQuery.data.session.closed_at
            )}
          />
        ) : null}
      </SectionCard>
    </Stack>
  );
}
