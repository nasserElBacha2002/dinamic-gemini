/**
 * Phase 3 / Phase 6 — run picker for multi-run aisles (test inventories).
 *
 * When `jobs` is non-empty, `valueJobId` must be a concrete job id (URL-aligned with the list query).
 */

import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  type SelectChangeEvent,
  Stack,
  Typography,
  Chip,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { JobSummary } from '../../../api/types';
import i18n from '../../../i18n';
import { getJobStatusLabel } from '../../../utils/jobStatus';

function shortId(id: string, n = 10): string {
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function formatJobLine(j: JobSummary): string {
  const parts: string[] = [shortId(j.id), getJobStatusLabel(j.status)];
  const t = j.created_at?.slice(0, 16)?.replace('T', ' ');
  if (t) parts.push(t);
  if (j.provider_name) parts.push(j.provider_name);
  if (j.model_name) parts.push(j.model_name);
  if (j.prompt_key) parts.push(j.prompt_key);
  if (j.prompt_version) parts.push(String(j.prompt_version));
  return parts.join(' · ');
}

export type AisleRunSelectorProps = {
  operationalJobId?: string | null;
  jobs: JobSummary[];
  /** Must match one of `jobs[].id` (page aligns URL + list query to this id). */
  valueJobId: string;
  onChange: (jobId: string) => void;
  disabled?: boolean;
};

export default function AisleRunSelector({
  operationalJobId,
  jobs,
  valueJobId,
  onChange,
  disabled,
}: AisleRunSelectorProps) {
  const { t } = useTranslation();
  const trimmed = valueJobId.trim();
  const validIds = new Set(jobs.map((j) => j.id));
  const fallback = jobs[0]?.id ?? '';
  const value = trimmed !== '' && validIds.has(trimmed) ? trimmed : fallback;

  const handleChange = (e: SelectChangeEvent<string>) => {
    onChange(e.target.value);
  };

  if (jobs.length === 0) {
    return null;
  }

  return (
    <FormControl size="small" sx={{ minWidth: 280, maxWidth: 480 }} disabled={disabled}>
      <InputLabel id="aisle-run-select-label">{t('results.browse_run')}</InputLabel>
      <Select
        labelId="aisle-run-select-label"
        label={t('results.browse_run')}
        value={value}
        onChange={handleChange}
        MenuProps={{
          PaperProps: { sx: { maxHeight: 360 } },
        }}
      >
        {jobs.map((j) => {
          const isOp = Boolean(operationalJobId != null && operationalJobId === j.id);
          const isBench = !isOp && j.status === 'succeeded';
          return (
            <MenuItem key={j.id} value={j.id}>
              <Stack spacing={0.5} sx={{ width: '100%', py: 0.25 }}>
                <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Typography variant="body2" component="span">
                    {formatJobLine(j)}
                  </Typography>
                  {isOp ? (
                    <Chip size="small" label={t('common.operational')} color="success" variant="outlined" />
                  ) : null}
                  {isBench ? (
                    <Chip size="small" label={t('common.benchmark')} color="default" variant="outlined" />
                  ) : null}
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  {[j.provider_name, j.model_name, j.prompt_key, j.prompt_version].filter(Boolean).join(' · ') ||
                    i18n.t('common.em_dash')}
                </Typography>
              </Stack>
            </MenuItem>
          );
        })}
      </Select>
    </FormControl>
  );
}
