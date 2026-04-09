/**
 * Phase 6 — pick two explicit runs for benchmark compare (read-only; separate from operational KPIs).
 */

import { useTranslation } from 'react-i18next';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Typography,
} from '@mui/material';
import type { JobSummary } from '../../api/types';

export type CompareRunsDialogProps = {
  open: boolean;
  onClose: () => void;
  jobs: JobSummary[];
  compareJobA: string;
  compareJobB: string;
  onCompareJobAChange: (id: string) => void;
  onCompareJobBChange: (id: string) => void;
  onConfirm: () => void;
};

export default function CompareRunsDialog({
  open,
  onClose,
  jobs,
  compareJobA,
  compareJobB,
  onCompareJobAChange,
  onCompareJobBChange,
  onConfirm,
}: CompareRunsDialogProps) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('benchmark.compare_two_runs_title')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('benchmark.compare_readonly_explain')}
        </Typography>
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel id="cmp-a-label">{t('results.run_a_label')}</InputLabel>
          <Select
            labelId="cmp-a-label"
            label={t('results.run_a_label')}
            value={compareJobA}
            onChange={(e) => onCompareJobAChange(String(e.target.value))}
          >
            {jobs.map((j) => (
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
            value={compareJobB}
            onChange={(e) => onCompareJobBChange(String(e.target.value))}
          >
            {jobs.map((j) => (
              <MenuItem key={`b-${j.id}`} value={j.id}>
                {j.id.slice(0, 10)}… · {j.status}
                {j.is_operational ? t('benchmark.operational_suffix') : ''}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button
          variant="contained"
          disabled={!compareJobA || !compareJobB || compareJobA === compareJobB}
          onClick={onConfirm}
        >
          {t('benchmark.open_compare')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
