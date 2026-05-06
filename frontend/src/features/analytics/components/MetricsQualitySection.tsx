import { useTranslation } from 'react-i18next';
import { Box, Skeleton, Typography } from '@mui/material';
import { SectionCard } from '../../../components/ui';
import { qualityPriority, translateQualityIssueType } from '../adapters/metricsFormatters';
import type { QualityPatternRow } from '../types';

export interface MetricsQualitySectionProps {
  isLoading: boolean;
  hasQualityData: boolean;
  rows: readonly QualityPatternRow[];
}

export function MetricsQualitySection({ isLoading, hasQualityData, rows }: MetricsQualitySectionProps) {
  const { t } = useTranslation();

  return (
    <SectionCard title={t('analytics.quality_patterns_title')} subtitle={t('analytics.quality_patterns_subtitle')}>
      {isLoading && !hasQualityData ? (
        <Skeleton variant="rounded" height={160} />
      ) : rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('analytics.empty_quality_filter')}
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {rows.map((row: QualityPatternRow) => (
            <Box
              key={row.issue_type}
              sx={{
                p: 1.25,
                border: 1,
                borderColor: 'divider',
                borderRadius: 1.5,
                bgcolor: qualityPriority(row.issue_type) <= 2 ? 'background.default' : 'transparent',
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="body2" fontWeight={qualityPriority(row.issue_type) <= 2 ? 600 : 500}>
                  {translateQualityIssueType(row.issue_type, t)}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                  {row.count}
                  {row.percentage != null ? ` · ${(row.percentage * 100).toFixed(1)}%` : ''}
                </Typography>
              </Box>
              <Box sx={{ height: 6, bgcolor: 'action.hover', borderRadius: 1, overflow: 'hidden' }}>
                <Box
                  sx={{
                    height: '100%',
                    width: `${Math.min(100, (row.percentage ?? 0) * 100)}%`,
                    bgcolor: 'secondary.main',
                  }}
                />
              </Box>
              {row.notes ? (
                <Typography variant="caption" color="text.secondary">
                  {row.notes}
                </Typography>
              ) : null}
            </Box>
          ))}
        </Box>
      )}
    </SectionCard>
  );
}
