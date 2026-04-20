/**
 * Shared job A/B selectors for benchmark compare (used by dialog and analytics page).
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { FormControl, InputLabel, MenuItem, Select, Typography } from '@mui/material';
import type { JobSummary } from '../../api/types';
import { wallClockSecondsFromJobTimestamps } from '../../utils/benchmarkExecutionTime';

export type CompareRunJobPickersProps = {
  jobs: JobSummary[];
  jobA: string;
  jobB: string;
  onJobAChange: (id: string) => void;
  onJobBChange: (id: string) => void;
  /** Optional intro line (e.g. dialog explain vs analytics page hint). */
  description?: string;
};

export default function CompareRunJobPickers({
  jobs,
  jobA,
  jobB,
  onJobAChange,
  onJobBChange,
  description,
}: CompareRunJobPickersProps) {
  const { t } = useTranslation();
  const sortedJobs = useMemo(() => {
    const list = [...jobs];
    list.sort((a, b) => {
      const da = wallClockSecondsFromJobTimestamps(a.started_at, a.finished_at);
      const db = wallClockSecondsFromJobTimestamps(b.started_at, b.finished_at);
      const ra = da ?? Number.POSITIVE_INFINITY;
      const rb = db ?? Number.POSITIVE_INFINITY;
      if (ra !== rb) return ra - rb;
      return b.created_at.localeCompare(a.created_at);
    });
    return list;
  }, [jobs]);
  const safeJobA = jobA && jobs.some((j) => j.id === jobA) ? jobA : '';
  const safeJobB = jobB && jobs.some((j) => j.id === jobB) ? jobB : '';
  return (
    <>
      {description ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
      ) : null}
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel id="cmp-a-label">{t('results.run_a_label')}</InputLabel>
        <Select
          labelId="cmp-a-label"
          label={t('results.run_a_label')}
          value={safeJobA}
          displayEmpty
          onChange={(e) => onJobAChange(String(e.target.value))}
        >
          <MenuItem value="" disabled>
            <em>{t('common.em_dash')}</em>
          </MenuItem>
          {sortedJobs.map((j) => (
            <MenuItem key={`a-${j.id}`} value={j.id}>
              {j.id.slice(0, 10)}… · {j.status}
              {j.is_operational ? t('benchmark.operational_suffix') : ''}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <FormControl fullWidth size="small">
        <InputLabel id="cmp-b-label">{t('results.run_b_label')}</InputLabel>
        <Select
          labelId="cmp-b-label"
          label={t('results.run_b_label')}
          value={safeJobB}
          displayEmpty
          onChange={(e) => onJobBChange(String(e.target.value))}
        >
          <MenuItem value="" disabled>
            <em>{t('common.em_dash')}</em>
          </MenuItem>
          {sortedJobs.map((j) => (
            <MenuItem key={`b-${j.id}`} value={j.id}>
              {j.id.slice(0, 10)}… · {j.status}
              {j.is_operational ? t('benchmark.operational_suffix') : ''}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </>
  );
}
