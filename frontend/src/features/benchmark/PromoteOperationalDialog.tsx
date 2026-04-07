/**
 * Phase 6 — promote a succeeded run to the aisle operational pointer (no automatic correction transfer).
 */

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
  const eligible = jobs.filter((j) => j.status === 'succeeded' && j.id !== operationalJobId);

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Promote run to operational</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          Updates only <strong>which job slice is operational</strong>. Other runs stay stored for benchmarking.
          Review edits apply to the operational slice afterward; corrections are not copied automatically from
          other runs.
        </Typography>
        <FormControl fullWidth size="small">
          <InputLabel id="promote-job-label">Succeeded run</InputLabel>
          <Select
            labelId="promote-job-label"
            label="Succeeded run"
            value={promoteJobId}
            onChange={(e) => onPromoteJobIdChange(String(e.target.value))}
          >
            {eligible.map((j) => (
              <MenuItem key={j.id} value={j.id}>
                {j.id.slice(0, 12)}… · {j.provider_name ?? '—'} · {j.prompt_key ?? '—'}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" color="warning" disabled={!promoteJobId || isPending} onClick={onConfirm}>
          {isPending ? 'Promoting…' : 'Confirm promote'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
