import { useTranslation } from 'react-i18next';
import { Alert, Box, Chip, Divider, Skeleton, Stack, Typography } from '@mui/material';
import { SectionCard } from '../../../components/ui';
import { interventionColor, interventionLabel } from '../adapters/metricsFormatters';
import type { ManualInterventionCategory } from '../types';

export interface MetricsManualInterventionSectionProps {
  notes: readonly string[];
  isLoading: boolean;
  hasManualInterventions: boolean;
  reviewedPositionsCount: number;
  supportedInterventions: readonly ManualInterventionCategory[];
  unsupportedInterventions: readonly ManualInterventionCategory[];
}

export function MetricsManualInterventionSection({
  notes,
  isLoading,
  hasManualInterventions,
  reviewedPositionsCount,
  supportedInterventions,
  unsupportedInterventions,
}: MetricsManualInterventionSectionProps) {
  const { t } = useTranslation();

  return (
    <>
      {notes.length ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {notes.join(' ')}
        </Alert>
      ) : null}
      <SectionCard
        title={t('analytics.manual_intervention_title')}
        subtitle={t('analytics.manual_intervention_subtitle')}
      >
        {isLoading && !hasManualInterventions ? (
          <Skeleton variant="rounded" height={220} />
        ) : supportedInterventions.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('analytics.no_manual_interventions_scope')}
          </Typography>
        ) : (
          <Stack spacing={1.5}>
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 2,
                flexWrap: 'wrap',
                p: 1.5,
                border: 1,
                borderColor: 'divider',
                borderRadius: 1.5,
                bgcolor: 'background.default',
              }}
            >
              <Typography variant="body2" color="text.secondary">
                {t('analytics.reviewed_positions_label')}
              </Typography>
              <Typography variant="body2" fontWeight={600}>
                {reviewedPositionsCount}
              </Typography>
            </Box>
            {supportedInterventions.map((item: ManualInterventionCategory) => (
              <Box key={item.category}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, mb: 0.5 }}>
                  <Typography variant="body2" fontWeight={600}>
                    {interventionLabel(item.category, t)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                    {item.count ?? 0}
                    {item.percentage != null ? ` · ${(item.percentage * 100).toFixed(1)}%` : ''}
                  </Typography>
                </Box>
                <Box sx={{ height: 8, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
                  <Box
                    sx={{
                      height: '100%',
                      width: `${Math.min(100, (item.percentage ?? 0) * 100)}%`,
                      bgcolor: interventionColor(item.category),
                    }}
                  />
                </Box>
                {item.notes ? (
                  <Typography variant="caption" color="text.secondary">
                    {item.notes}
                  </Typography>
                ) : null}
              </Box>
            ))}
            {unsupportedInterventions.length ? (
              <>
                <Divider />
                <Typography variant="caption" color="text.secondary">
                  {t('analytics.awaiting_backend_support')}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {unsupportedInterventions.map((item: ManualInterventionCategory) => (
                    <Chip
                      key={item.category}
                      label={t('analytics.intervention_unavailable_chip', {
                        label: interventionLabel(item.category, t),
                      })}
                      size="small"
                      variant="outlined"
                    />
                  ))}
                </Stack>
              </>
            ) : null}
          </Stack>
        )}
      </SectionCard>
    </>
  );
}
