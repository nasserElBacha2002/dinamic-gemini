/**
 * Phase 6 — promote a succeeded run to the aisle operational pointer (no automatic correction transfer).
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
import i18n from '../../i18n';

export type PromoteOperationalDialogProps = {
  open: boolean;
  onClose: () => void;
  jobs: JobSummary[];
  operationalJobId: string | null;
  promoteJobId: string;
  onPromoteJobIdChange: (id: string) => void;
  onConfirm: () => void;
  isPending: boolean;
};

export default function PromoteOperationalDialog({
  open,
  onClose,
  jobs,
  operationalJobId,
  promoteJobId,
  onPromoteJobIdChange,
  onConfirm,
  isPending,
}: PromoteOperationalDialogProps) {
  const { t } = useTranslation();
  const eligible = jobs.filter((j) => j.status === 'succeeded' && j.id !== operationalJobId);
  const dash = i18n.t('common.em_dash');

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>{t('benchmark.promote_title')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          {t('benchmark.promote_body')}
        </Typography>
        <FormControl fullWidth size="small">
          <InputLabel id="promote-job-label">{t('benchmark.succeeded_run_label')}</InputLabel>
          <Select
            labelId="promote-job-label"
            label={t('benchmark.succeeded_run_label')}
            value={promoteJobId}
            onChange={(e) => onPromoteJobIdChange(String(e.target.value))}
          >
            {eligible.map((j) => (
              <MenuItem key={j.id} value={j.id}>
                {j.id.slice(0, 12)}… · {j.provider_name ?? dash} · {j.prompt_key ?? dash}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" color="warning" disabled={!promoteJobId || isPending} onClick={onConfirm}>
          {isPending ? t('benchmark.promoting') : t('benchmark.confirm_promote')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
