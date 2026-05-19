import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { Alert, Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { AisleBenchmarkCompareManyResponse } from '../../../../api/types';
import { getRunModelLabel } from '../../adapters/compareRunLabels';

type CompareContextWarningsProps = {
  data: AisleBenchmarkCompareManyResponse;
  compact?: boolean;
};

export default function CompareContextWarnings({ data, compact = false }: CompareContextWarningsProps) {
  const { t } = useTranslation();

  const promptLines = (data.jobs ?? [])
    .map((job) => {
      const key = (job.prompt_key ?? '').trim();
      const version = (job.prompt_version ?? '').trim();
      if (!key && !version) return null;
      return t('compare_many.benchmark.promptMetadata', {
        run: getRunModelLabel(job, t),
        promptKey: key || '—',
        promptVersion: version || '—',
      });
    })
    .filter((line): line is string => Boolean(line));

  const bullets = [
    t('compare_many.benchmark.notRecommendation'),
    t('compare_many.benchmark.sameAisleContext'),
    t('compare_many.benchmark.neutralQuantityHelper'),
    t('compare_many.benchmark.needsReviewNotCorrections'),
    t('compare_many.benchmark.costSnapshotHelper'),
    t('compare_many.benchmark.diffDependsOnPrompt'),
  ];

  return (
    <Alert
      severity="info"
      icon={<InfoOutlinedIcon fontSize="small" />}
      data-testid="compare-benchmark-context-warnings"
      sx={{ mb: compact ? 1.5 : 2 }}
    >
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>
        {t('compare_many.benchmark.contextTitle')}
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.25 }}>
        {bullets.map((text) => (
          <Typography key={text} component="li" variant="body2" sx={{ mb: 0.35 }}>
            {text}
          </Typography>
        ))}
      </Box>
      {promptLines.length > 0 ? (
        <Box sx={{ mt: 1 }}>
          {promptLines.map((line) => (
            <Typography key={line} variant="caption" color="text.secondary" display="block">
              {line}
            </Typography>
          ))}
        </Box>
      ) : null}
    </Alert>
  );
}
