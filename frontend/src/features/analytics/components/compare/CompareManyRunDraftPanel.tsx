import {
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Tooltip,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { JobSummary } from '../../../../api/types';
import {
  getRunModelLabel,
  getRunPickerMenuSecondaryLine,
} from '../../adapters/compareRunLabels';

type AisleOption = {
  id: string;
  code: string;
};

type CompareManyRunDraftPanelProps = {
  aisles: AisleOption[];
  jobs: JobSummary[];
  jobsForDisplayFallback: JobSummary[];
  draftAisleId: string;
  draftJobIds: string[];
  baselineSelectValue: string;
  maxCompareJobs: number;
  dirty: boolean;
  draftError: string | null;
  onAisleChange: (nextAisleId: string) => void;
  onDraftJobIdsChange: (nextJobIds: string[]) => void;
  onBaselineChange: (nextBaseline: string) => void;
  onApply: () => void;
  aisleLabel: string;
  jobsLabel: string;
  baselineLabel: string;
  applyLabel: string;
  dirtyLabel: string;
};

export default function CompareManyRunDraftPanel({
  aisles,
  jobs,
  jobsForDisplayFallback,
  draftAisleId,
  draftJobIds,
  baselineSelectValue,
  maxCompareJobs,
  dirty,
  draftError,
  onAisleChange,
  onDraftJobIdsChange,
  onBaselineChange,
  onApply,
  aisleLabel,
  jobsLabel,
  baselineLabel,
  applyLabel,
  dirtyLabel,
}: CompareManyRunDraftPanelProps) {
  const { t } = useTranslation();

  const resolveJob = (id: string): JobSummary | undefined =>
    jobs.find((job) => job.id === id) ?? jobsForDisplayFallback.find((job) => job.id === id);

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="compare-many-controls">
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 }}>
        <FormControl size="small">
          <InputLabel id="compare-many-aisle-label">{aisleLabel}</InputLabel>
          <Select
            labelId="compare-many-aisle-label"
            value={draftAisleId}
            label={aisleLabel}
            onChange={(e) => onAisleChange(String(e.target.value))}
          >
            {aisles.map((aisle) => (
              <MenuItem key={aisle.id} value={aisle.id}>
                {aisle.code}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small">
          <InputLabel id="compare-many-jobids-label">{jobsLabel}</InputLabel>
          <Select
            labelId="compare-many-jobids-label"
            multiple
            value={draftJobIds}
            label={jobsLabel}
            onChange={(e) => onDraftJobIdsChange((e.target.value as string[]).slice(0, maxCompareJobs))}
            renderValue={(selected) => (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, maxWidth: '100%' }}>
                {(selected as string[]).map((id) => {
                  const job = resolveJob(id);
                  if (!job) {
                    return (
                      <Chip key={id} size="small" label={id.slice(0, 8)} />
                    );
                  }
                  return (
                    <Tooltip key={id} title={id}>
                      <Chip size="small" label={getRunModelLabel(job, t)} sx={{ maxWidth: '100%' }} />
                    </Tooltip>
                  );
                })}
              </Box>
            )}
          >
            {jobs.map((job) => (
              <MenuItem
                key={job.id}
                value={job.id}
                disabled={!draftJobIds.includes(job.id) && draftJobIds.length >= maxCompareJobs}
              >
                <ListItemText
                  primary={getRunModelLabel(job, t)}
                  secondary={getRunPickerMenuSecondaryLine(job, t)}
                  primaryTypographyProps={{ variant: 'body2' }}
                  secondaryTypographyProps={{
                    variant: 'caption',
                    sx: { whiteSpace: 'normal', wordBreak: 'break-word' },
                  }}
                />
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small">
          <InputLabel id="compare-many-baseline-label">{baselineLabel}</InputLabel>
          <Select
            labelId="compare-many-baseline-label"
            value={baselineSelectValue}
            label={baselineLabel}
            onChange={(e) => onBaselineChange(String(e.target.value))}
            renderValue={(id) => {
              const job = resolveJob(String(id));
              return job ? getRunModelLabel(job, t) : String(id).slice(0, 8);
            }}
          >
            {draftJobIds.map((id) => {
              const job = resolveJob(id);
              if (!job) {
                return (
                  <MenuItem key={id} value={id}>
                    {id.slice(0, 8)}…
                  </MenuItem>
                );
              }
              return (
                <MenuItem key={id} value={id}>
                  <ListItemText
                    primary={getRunModelLabel(job, t)}
                    secondary={getRunPickerMenuSecondaryLine(job, t)}
                    primaryTypographyProps={{ variant: 'body2' }}
                    secondaryTypographyProps={{
                      variant: 'caption',
                      sx: { whiteSpace: 'normal', wordBreak: 'break-word' },
                    }}
                  />
                </MenuItem>
              );
            })}
          </Select>
        </FormControl>

        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Button variant="contained" onClick={onApply} disabled={Boolean(draftError) || !dirty}>
            {applyLabel}
          </Button>
          {dirty ? <Chip size="small" label={dirtyLabel} variant="outlined" /> : null}
        </Box>
      </Box>
      {draftError ? (
        <Typography variant="caption" color="error" display="block" sx={{ mt: 1 }}>
          {draftError}
        </Typography>
      ) : null}
    </Paper>
  );
}
