import { useTranslation } from 'react-i18next';
import { Box, Skeleton, Stack, Typography } from '@mui/material';
import { SectionCard } from '../../../components/ui';

export interface MetricsResolutionFlowStage {
  label: string;
  value: number;
  helper: string;
}

export interface MetricsResolutionFlowSectionProps {
  isLoading: boolean;
  hasSummary: boolean;
  hasOperatorUnknownRate: boolean;
  resolutionFlowStages: readonly MetricsResolutionFlowStage[];
  totalPositionsCount: number;
  manualCorrectionCount: number;
  operatorMarkedUnknownCount: number;
}

export function MetricsResolutionFlowSection({
  isLoading,
  hasSummary,
  hasOperatorUnknownRate,
  resolutionFlowStages,
  totalPositionsCount,
  manualCorrectionCount,
  operatorMarkedUnknownCount,
}: MetricsResolutionFlowSectionProps) {
  const { t } = useTranslation();

  return (
    <SectionCard title={t('analytics.resolution_flow_title')} subtitle={t('analytics.resolution_flow_subtitle')}>
      {isLoading && !hasSummary ? (
        <Skeleton variant="rounded" height={220} />
      ) : (
        <Stack spacing={1.25}>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: 'repeat(2, minmax(0, 1fr))',
                md: hasOperatorUnknownRate ? 'repeat(3, minmax(0, 1fr))' : 'repeat(4, minmax(0, 1fr))',
              },
              gap: 1.5,
              minWidth: 0,
              width: '100%',
            }}
          >
            {resolutionFlowStages.map((item) => (
              <Box key={item.label} sx={{ minWidth: 0 }}>
                <Box
                  sx={{
                    border: 1,
                    borderColor: 'divider',
                    borderRadius: 1.5,
                    p: 1.5,
                    height: '100%',
                    bgcolor: 'background.default',
                  }}
                >
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    {item.label}
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {item.value}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {item.helper}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Box>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: `repeat(${resolutionFlowStages.length}, minmax(0, 1fr))`,
              gap: 1,
            }}
          >
            {resolutionFlowStages.map((item, index) => (
              <Box
                key={`${item.label}-bar`}
                sx={{
                  minWidth: 0,
                }}
              >
                <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                  {index < resolutionFlowStages.length - 1
                    ? t('analytics.resolution_step')
                    : t('analytics.resolution_outcome')}
                </Typography>
                <Box sx={{ height: 10, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
                  <Box
                    sx={{
                      height: '100%',
                      width: `${totalPositionsCount > 0 ? Math.min(100, (item.value / totalPositionsCount) * 100) : 0}%`,
                      bgcolor:
                        index === resolutionFlowStages.length - 1 && hasOperatorUnknownRate
                          ? 'warning.main'
                          : 'primary.main',
                    }}
                  />
                </Box>
              </Box>
            ))}
          </Box>
          <Typography variant="caption" color="text.secondary">
            {t('analytics.manual_corrections_in_scope', { count: manualCorrectionCount })}
            {hasOperatorUnknownRate ? t('analytics.operator_unknown_outcomes', { count: operatorMarkedUnknownCount }) : ''}
          </Typography>
        </Stack>
      )}
    </SectionCard>
  );
}
