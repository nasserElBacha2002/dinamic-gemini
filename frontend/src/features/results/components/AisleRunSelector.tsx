/**
 * Phase 3 — minimal run picker for multi-run aisles (backend-resolved default vs explicit job).
 *
 * `valueJobId` is the effective run shown in the control (from URL and/or backend-resolved slice).
 */

import { FormControl, InputLabel, MenuItem, Select, type SelectChangeEvent, Stack, Typography } from '@mui/material';
import type { JobSummary } from '../../../api/types';

function shortId(id: string, n = 10): string {
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function formatJobLine(j: JobSummary): string {
  const parts: string[] = [shortId(j.id), j.status];
  const t = j.created_at?.slice(0, 16)?.replace('T', ' ');
  if (t) parts.push(t);
  if (j.provider_name) parts.push(j.provider_name);
  return parts.join(' · ');
}

export type AisleRunSelectorProps = {
  operationalJobId?: string | null;
  jobs: JobSummary[];
  /**
   * Effective run shown as selected: explicit URL job, or backend-resolved job when no URL pin.
   * Empty string / null → Default (API resolver) row.
   */
  valueJobId: string | null;
  onChange: (jobId: string | null) => void;
  disabled?: boolean;
  loading?: boolean;
  /** True when `?jobId=` is present (explicit URL pin). */
  urlPinned?: boolean;
};

export default function AisleRunSelector({
  operationalJobId,
  jobs,
  valueJobId,
  onChange,
  disabled,
  loading,
  urlPinned = false,
}: AisleRunSelectorProps) {
  const trimmed = valueJobId?.trim() ?? '';
  const validIds = new Set(jobs.map((j) => j.id));
  const value = trimmed !== '' && validIds.has(trimmed) ? trimmed : '';

  const handleChange = (e: SelectChangeEvent<string>) => {
    const v = e.target.value;
    onChange(v === '' ? null : v);
  };

  if (jobs.length === 0 && !loading) {
    return null;
  }

  return (
    <FormControl size="small" sx={{ minWidth: 280, maxWidth: 420 }} disabled={disabled || loading}>
      <InputLabel id="aisle-run-select-label">Browse run</InputLabel>
      <Select
        labelId="aisle-run-select-label"
        label="Browse run"
        value={value}
        onChange={handleChange}
        displayEmpty
      >
        <MenuItem value="">
          <Stack spacing={0.25}>
            <Typography variant="body2">Default (API resolver)</Typography>
            <Typography variant="caption" color="text.secondary">
              {urlPinned
                ? 'Clears ?jobId= and uses the API default resolver for this aisle'
                : 'No ?jobId= in URL — backend picks operational / legacy / latest-succeeded'}
            </Typography>
          </Stack>
        </MenuItem>
        {jobs.map((j) => {
          const isOp = operationalJobId != null && operationalJobId === j.id;
          return (
            <MenuItem key={j.id} value={j.id}>
              <Stack spacing={0.25} sx={{ width: '100%' }}>
                <Typography variant="body2" component="span">
                  {formatJobLine(j)}
                  {isOp ? (
                    <Typography component="span" variant="caption" sx={{ ml: 1, color: 'success.main' }}>
                      operational
                    </Typography>
                  ) : null}
                </Typography>
                {(j.model_name || j.prompt_key) && (
                  <Typography variant="caption" color="text.secondary" noWrap>
                    {[j.model_name, j.prompt_key].filter(Boolean).join(' · ')}
                  </Typography>
                )}
              </Stack>
            </MenuItem>
          );
        })}
      </Select>
    </FormControl>
  );
}
