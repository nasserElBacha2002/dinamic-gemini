import { useState } from 'react';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { Alert, Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { AisleBenchmarkCompareManyResponse } from '../../../../api/types';
import { getRunModelLabel } from '../../adapters/compareRunLabels';

type CompareContextWarningsProps = {
  data: AisleBenchmarkCompareManyResponse;
  compact?: boolean;
};

const COMPACT_PRIMARY_KEYS = [
  'compare_many.benchmark.notRecommendation',
  'compare_many.benchmark.neutralQuantityHelper',
  'compare_many.benchmark.costSnapshotHelper',
] as const;

const FULL_BULLET_KEYS = [
  'compare_many.benchmark.notRecommendation',
  'compare_many.benchmark.sameAisleContext',
  'compare_many.benchmark.neutralQuantityHelper',
  'compare_many.benchmark.needsReviewNotCorrections',
  'compare_many.benchmark.costSnapshotHelper',
  'compare_many.benchmark.diffDependsOnPrompt',
] as const;

export default function CompareContextWarnings({ data, compact = false }: CompareContextWarningsProps) {
  const { t } = useTranslation();
  const [showAllNotes, setShowAllNotes] = useState(false);

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

  const fullBullets = FULL_BULLET_KEYS.map((key) => t(key));
  const compactPrimary = COMPACT_PRIMARY_KEYS.map((key) => t(key));
  const compactHiddenCount = fullBullets.length - compactPrimary.length;

  const visibleBullets =
    compact && !showAllNotes ? compactPrimary : fullBullets;

  return (
    <Alert
      severity="info"
      icon={<InfoOutlinedIcon fontSize="small" />}
      data-testid="compare-benchmark-context-warnings"
      data-compact={compact ? 'true' : 'false'}
      sx={{ mb: compact ? 1.5 : 2 }}
    >
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>
        {t('compare_many.benchmark.contextTitle')}
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.25 }}>
        {visibleBullets.map((text) => (
          <Typography key={text} component="li" variant="body2" sx={{ mb: 0.35 }}>
            {text}
          </Typography>
        ))}
      </Box>
      {compact && !showAllNotes && compactHiddenCount > 0 ? (
        <Button
          size="small"
          variant="text"
          sx={{ mt: 0.5, px: 0, minWidth: 0 }}
          data-testid="compare-benchmark-context-more-notes"
          onClick={() => setShowAllNotes(true)}
        >
          {t('compare_many.benchmark.moreNotes', { count: compactHiddenCount })}
        </Button>
      ) : null}
      {!compact && promptLines.length > 0 ? (
        <Box sx={{ mt: 1 }}>
          {promptLines.map((line) => (
            <Typography key={line} variant="caption" color="text.secondary" display="block">
              {line}
            </Typography>
          ))}
        </Box>
      ) : null}
      {compact && showAllNotes && promptLines.length > 0 ? (
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
