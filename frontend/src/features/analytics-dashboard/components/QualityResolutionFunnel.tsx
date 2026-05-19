import { Box, Typography } from '@mui/material';
import type { ResolutionFlowStageViewModel } from '../../analytics/adapters/metricsViewModel';

export interface QualityResolutionFunnelProps {
  stages: readonly ResolutionFlowStageViewModel[];
  emptyText: string;
  'data-testid'?: string;
}

export function QualityResolutionFunnel({ stages, emptyText, 'data-testid': testId }: QualityResolutionFunnelProps) {
  if (!stages.length) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid={testId ? `${testId}-empty` : undefined}>
        {emptyText}
      </Typography>
    );
  }

  const max = Math.max(...stages.map((stage) => stage.value), 1);
  const ariaLabel = stages.map((stage) => `${stage.label} ${stage.value}`).join(', ');

  return (
    <Box
      role="img"
      aria-label={ariaLabel}
      data-testid={testId}
      sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}
    >
      {stages.map((stage) => {
        const widthPct = Math.max(4, (stage.value / max) * 100);
        return (
          <Box key={stage.label} data-testid={testId ? `${testId}-stage-${stage.label}` : undefined}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, mb: 0.35 }}>
              <Typography variant="caption" color="text.secondary" noWrap title={stage.label}>
                {stage.label}
              </Typography>
              <Typography variant="caption" fontWeight={600}>
                {stage.value}
              </Typography>
            </Box>
            <Box sx={{ height: 10, bgcolor: 'action.hover', borderRadius: 999, overflow: 'hidden' }}>
              <Box sx={{ height: '100%', width: `${widthPct}%`, bgcolor: 'primary.main', borderRadius: 999 }} />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
