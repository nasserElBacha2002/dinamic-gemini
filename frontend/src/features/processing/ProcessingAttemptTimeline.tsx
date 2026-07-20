import { useTranslation } from 'react-i18next';
import { Box, Paper, Stack, Typography } from '@mui/material';
import { StatusBadge } from '../../components/ui';
import { formatDate } from '../../utils/formatDate';
import { processingStatusLabel, processingStatusToSemantic } from './utils/processingStatus';

export interface ProcessingAttemptTimelineProps {
  attempts: Array<Record<string, unknown>>;
  historicalIncomplete?: boolean;
}

function readString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export default function ProcessingAttemptTimeline({
  attempts,
  historicalIncomplete,
}: ProcessingAttemptTimelineProps) {
  const { t } = useTranslation();

  if (historicalIncomplete) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="processing-attempts-historical">
        {t('processing.attempts.historicalUnavailable')}
      </Typography>
    );
  }

  if (!attempts.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="processing-attempts-empty">
        {t('processing.attempts.empty')}
      </Typography>
    );
  }

  return (
    <Stack spacing={1} data-testid="processing-attempt-timeline">
      {attempts.map((attempt, index) => {
        const status = readString(attempt, 'status');
        const strategy = readString(attempt, 'strategy') ?? readString(attempt, 'executed_strategy');
        const startedAt = readString(attempt, 'started_at') ?? readString(attempt, 'created_at');
        const errorCode = readString(attempt, 'error_code') ?? readString(attempt, 'last_error_code');
        const key = readString(attempt, 'id') ?? `attempt-${index}`;

        return (
          <Paper key={key} variant="outlined" sx={{ p: 1.25 }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', mb: 0.5 }}>
              <Typography variant="subtitle2">
                {t('processing.attempts.item', { number: index + 1 })}
              </Typography>
              {status ? (
                <StatusBadge
                  label={processingStatusLabel(status, t)}
                  semantic={processingStatusToSemantic(status)}
                />
              ) : null}
            </Box>
            {strategy ? (
              <Typography variant="caption" color="text.secondary" display="block">
                {t('processing.attempts.strategy', { value: strategy })}
              </Typography>
            ) : null}
            {startedAt ? (
              <Typography variant="caption" color="text.secondary" display="block">
                {t('processing.attempts.startedAt', { value: formatDate(startedAt) })}
              </Typography>
            ) : null}
            {errorCode ? (
              <Typography variant="caption" color="error" display="block">
                {t('processing.attempts.errorCode', { value: errorCode })}
              </Typography>
            ) : null}
          </Paper>
        );
      })}
    </Stack>
  );
}
