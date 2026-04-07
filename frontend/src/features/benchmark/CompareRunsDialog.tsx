/**
 * Phase 6 — pick two explicit runs for benchmark compare (read-only; separate from operational KPIs).
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
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Compare two runs</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Benchmark compare is read-only and uses a separate path from operational analytics. It does not change
          which run is operational.
        </Typography>
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel id="cmp-a-label">Run A</InputLabel>
          <Select
            labelId="cmp-a-label"
            label="Run A"
            value={compareJobA}
            onChange={(e) => onCompareJobAChange(String(e.target.value))}
          >
            {jobs.map((j) => (
              <MenuItem key={`a-${j.id}`} value={j.id}>
                {j.id.slice(0, 10)}… · {j.status}
                {j.is_operational ? ' · operational' : ''}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl fullWidth size="small">
          <InputLabel id="cmp-b-label">Run B</InputLabel>
          <Select
            labelId="cmp-b-label"
            label="Run B"
            value={compareJobB}
            onChange={(e) => onCompareJobBChange(String(e.target.value))}
          >
            {jobs.map((j) => (
              <MenuItem key={`b-${j.id}`} value={j.id}>
                {j.id.slice(0, 10)}… · {j.status}
                {j.is_operational ? ' · operational' : ''}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!compareJobA || !compareJobB || compareJobA === compareJobB}
          onClick={onConfirm}
        >
          Open compare
        </Button>
      </DialogActions>
    </Dialog>
  );
}
