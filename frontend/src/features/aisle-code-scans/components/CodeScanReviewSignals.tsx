import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Chip,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { useAisleCodeScanReviewSignals } from '../hooks/useAisleCodeScanReviewSignals';
import type { CodeScanReviewSignal, CodeScanSignalSeverity } from '../../../api/types/codeScans';

export interface CodeScanReviewSignalsProps {
  inventoryId: string;
  aisleId: string;
  enabled: boolean;
}

type SeverityFilter = 'all' | CodeScanSignalSeverity;

function matchesFilter(signal: CodeScanReviewSignal, filter: SeverityFilter): boolean {
  if (filter === 'all') return true;
  return signal.severity === filter;
}

export default function CodeScanReviewSignals({
  inventoryId,
  aisleId,
  enabled,
}: CodeScanReviewSignalsProps) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<SeverityFilter>('all');
  const { data, isLoading, isError, error } = useAisleCodeScanReviewSignals(
    inventoryId,
    aisleId,
    { enabled }
  );

  const filtered = useMemo(() => {
    const signals = data?.signals ?? [];
    return signals.filter((s) => matchesFilter(s, filter));
  }, [data?.signals, filter]);

  const summary = data?.summary;

  if (!enabled) {
    return null;
  }

  return (
    <Box data-testid="code-scan-review-signals" sx={{ mb: 3 }}>
      <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 0.5 }}>
        {t('aisleCodeScans.signals.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {t('aisleCodeScans.signals.description')}
      </Typography>

      {isLoading ? (
        <Typography variant="body2" color="text.secondary">
          {t('aisleCodeScans.states.loading')}
        </Typography>
      ) : null}

      {isError ? (
        <Alert severity="warning">
          {resolveApiErrorMessage(error, 'aisleCodeScans.signals.loadError')}
        </Alert>
      ) : null}

      {!isLoading && !isError && data ? (
        <>
          {summary ? (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
              <Chip size="small" label={`${t('aisleCodeScans.signals.matchedCount')}: ${summary.matched_codes}`} />
              <Chip
                size="small"
                color="warning"
                variant="outlined"
                label={`${t('aisleCodeScans.signals.unmatchedCount')}: ${summary.unmatched_codes}`}
              />
              <Chip
                size="small"
                color="warning"
                variant="outlined"
                label={`${t('aisleCodeScans.signals.multipleCount')}: ${summary.multiple_candidates}`}
              />
            </Stack>
          ) : null}

          <ToggleButtonGroup
            size="small"
            exclusive
            value={filter}
            onChange={(_e, v: SeverityFilter | null) => {
              if (v) setFilter(v);
            }}
            sx={{ mb: 1.5 }}
          >
            <ToggleButton value="all">{t('aisleCodeScans.signals.filterAll')}</ToggleButton>
            <ToggleButton value="attention">{t('aisleCodeScans.signals.attention')}</ToggleButton>
            <ToggleButton value="warning">{t('aisleCodeScans.signals.warning')}</ToggleButton>
            <ToggleButton value="info">{t('aisleCodeScans.signals.info')}</ToggleButton>
          </ToggleButtonGroup>

          {filtered.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('aisleCodeScans.signals.empty')}
            </Typography>
          ) : (
            <Stack spacing={1}>
              {filtered.slice(0, 12).map((signal) => (
                <Box
                  key={signal.id}
                  sx={{
                    py: 1,
                    px: 1.5,
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t(`aisleCodeScans.signals.${signal.severity}`)}
                  </Typography>
                  <Typography variant="body2">{signal.message}</Typography>
                  {signal.code_value ? (
                    <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
                      {signal.code_value}
                    </Typography>
                  ) : null}
                </Box>
              ))}
            </Stack>
          )}
        </>
      ) : null}
    </Box>
  );
}
