import { useTranslation } from 'react-i18next';
import { Box, Button, Paper, Stack, Typography } from '@mui/material';
import { LoadingBlock } from '../../components/ui';
import { formatDate } from '../../utils/formatDate';
import type { ProcessingEventRecord } from '../../api/types/processing';

export interface ProcessingLogsTimelineProps {
  events: ProcessingEventRecord[];
  isLoading?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loadMorePending?: boolean;
}

function eventLevelColor(level: string | null | undefined): 'error' | 'warning' | 'info' | 'text.secondary' {
  const normalized = String(level ?? '').toLowerCase();
  if (normalized === 'error') return 'error';
  if (normalized === 'warning') return 'warning';
  if (normalized === 'info') return 'info';
  return 'text.secondary';
}

export default function ProcessingLogsTimeline({
  events,
  isLoading,
  hasMore,
  onLoadMore,
  loadMorePending,
}: ProcessingLogsTimelineProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return <LoadingBlock message={t('processing.logs.loading')} py={2} />;
  }

  if (!events.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="processing-logs-empty">
        {t('processing.logs.empty')}
      </Typography>
    );
  }

  return (
    <Stack spacing={1} data-testid="processing-logs-timeline">
      {events.map((event) => (
        <Paper key={event.id} variant="outlined" sx={{ p: 1.25 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'baseline' }}>
            <Typography variant="caption" color="text.secondary">
              {formatDate(event.timestamp)}
            </Typography>
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              {event.event_type}
            </Typography>
            {event.level ? (
              <Typography variant="caption" color={eventLevelColor(event.level)}>
                {event.level}
              </Typography>
            ) : null}
          </Box>
          {event.message ? (
            <Typography variant="body2" sx={{ mt: 0.5, wordBreak: 'break-word' }}>
              {event.message}
            </Typography>
          ) : null}
        </Paper>
      ))}
      {hasMore && onLoadMore ? (
        <Button size="small" variant="outlined" onClick={onLoadMore} disabled={loadMorePending}>
          {loadMorePending ? t('common.loading') : t('processing.logs.loadMore')}
        </Button>
      ) : null}
    </Stack>
  );
}
