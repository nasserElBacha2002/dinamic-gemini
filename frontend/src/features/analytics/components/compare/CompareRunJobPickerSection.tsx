import { Box, Button, Paper, Typography } from '@mui/material';
import CompareRunJobPickers from '../../../../components/compare/CompareRunJobPickers';

type CompareRunJobPickerSectionProps = {
  visible: boolean;
  jobs: Parameters<typeof CompareRunJobPickers>[0]['jobs'];
  draftJobA: string;
  draftJobB: string;
  onDraftJobAChange: (jobA: string) => void;
  onDraftJobBChange: (jobB: string) => void;
  onApplyJobs: () => void;
  sectionTitle: string;
  description: string;
  applyLabel: string;
  recentRunsLabel?: string;
};

export default function CompareRunJobPickerSection({
  visible,
  jobs,
  draftJobA,
  draftJobB,
  onDraftJobAChange,
  onDraftJobBChange,
  onApplyJobs,
  sectionTitle,
  description,
  applyLabel,
  recentRunsLabel,
}: CompareRunJobPickerSectionProps) {
  if (!visible) return null;

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="compare-runs-job-scope">
      <Typography variant="subtitle2" gutterBottom>
        {sectionTitle}
      </Typography>
      <CompareRunJobPickers
        jobs={jobs}
        jobA={draftJobA}
        jobB={draftJobB}
        onJobAChange={onDraftJobAChange}
        onJobBChange={onDraftJobBChange}
        description={description}
      />
      <Box sx={{ mt: 2 }}>
        <Button variant="contained" disabled={!draftJobA || !draftJobB || draftJobA === draftJobB} onClick={onApplyJobs}>
          {applyLabel}
        </Button>
      </Box>
      {recentRunsLabel ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
          {recentRunsLabel}
        </Typography>
      ) : null}
    </Paper>
  );
}
