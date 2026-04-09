/**
 * Phase 6 — pick two explicit runs for benchmark compare (read-only; separate from operational KPIs).
 */

import { useTranslation } from 'react-i18next';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import CompareRunJobPickers from '../../components/compare/CompareRunJobPickers';
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
        <CompareRunJobPickers
          jobs={jobs}
          jobA={compareJobA}
          jobB={compareJobB}
          onJobAChange={onCompareJobAChange}
          onJobBChange={onCompareJobBChange}
          description={t('benchmark.compare_readonly_explain')}
        />
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
