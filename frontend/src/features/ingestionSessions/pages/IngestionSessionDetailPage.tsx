import ArrowBackOutlinedIcon from '@mui/icons-material/ArrowBackOutlined';
import { Button, Stack } from '@mui/material';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
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

export function hasRequiredDetailParams(inventoryId: string, sessionId: string | undefined): boolean {
  return Boolean(inventoryId.trim() && sessionId);
}

export default function IngestionSessionDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();
  const [searchParams] = useSearchParams();
  const inventoryId = searchParams.get('inventoryId') ?? '';

  const detailQuery = useCaptureSessionDetail(inventoryId || undefined, sessionId || undefined, {
    enabled: hasRequiredDetailParams(inventoryId, sessionId),
  });
  const closeMutation = useCloseCaptureSession();

  const errorMessage = useMemo(() => {
    const err = detailQuery.error || closeMutation.error;
    if (!err) return null;
    return resolveApiErrorMessage(err, 'errors.request_failed');
  }, [closeMutation.error, detailQuery.error]);

  if (!hasRequiredDetailParams(inventoryId, sessionId)) {
    return (
      <ErrorAlert
        message={t('ingestion_sessions.errors.missing_inventory_or_session')}
        onRetry={() => navigate(ROUTE_INGESTION_SESSIONS)}
      />
    );
  }
  const resolvedSessionId = sessionId as string;

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('ingestion_sessions.detail.page_title')}
        actions={
          <Button
            variant="outlined"
            startIcon={<ArrowBackOutlinedIcon />}
            onClick={() => navigate(ROUTE_INGESTION_SESSIONS)}
          >
            {t('ingestion_sessions.actions.back_to_sessions')}
          </Button>
        }
      />

      {errorMessage ? <ErrorAlert message={errorMessage} onRetry={() => detailQuery.refetch()} /> : null}

      <SectionCard title={t('ingestion_sessions.detail.section_title')}>
        {detailQuery.data ? (
          <ImportSessionDetail
            detail={detailQuery.data}
            onRefresh={() => {
              void detailQuery.refetch();
            }}
            onCloseSession={() => {
              void closeMutation.mutateAsync({
                inventoryId,
                aisleId: detailQuery.data.session.aisle_id,
                sessionId: resolvedSessionId,
              });
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
