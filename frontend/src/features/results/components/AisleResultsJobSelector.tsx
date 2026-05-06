import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { JobSummary } from '../../../api/types';
import AisleRunSelector from './AisleRunSelector';

export interface AisleResultsJobSelectorProps {
  visible: boolean;
  isJobsLoading: boolean;
  jobs: JobSummary[];
  pickedRunJobId: string | null;
  operationalJobId: string | null;
  resultContextSource: string | null | undefined;
  visibleJobId: string | null;
  onRunSelectionChange: (next: string) => void;
}

export default function AisleResultsJobSelector({
  visible,
  isJobsLoading,
  jobs,
  pickedRunJobId,
  operationalJobId,
  resultContextSource,
  visibleJobId,
  onRunSelectionChange,
}: AisleResultsJobSelectorProps) {
  const { t } = useTranslation();

  if (!visible) return null;

  return (
    <Box sx={{ mb: 2, display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
      {isJobsLoading && jobs.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('common.loading')}
        </Typography>
      ) : jobs.length > 0 && pickedRunJobId ? (
        <AisleRunSelector
          operationalJobId={operationalJobId}
          jobs={jobs}
          valueJobId={pickedRunJobId}
          onChange={onRunSelectionChange}
        />
      ) : null}
      {resultContextSource ? (
        <Typography variant="caption" color="text.secondary">
          {t('positions.resolved_line', {
            source: resultContextSource,
            jobSuffix: visibleJobId ? t('positions.resolved_job_bit', { id: `${visibleJobId.slice(0, 10)}…` }) : '',
            noPinNote: '',
          })}
        </Typography>
      ) : null}
    </Box>
  );
}
