import { Paper, Typography } from '@mui/material';

/** Sprint 2.1 placeholder — Re diseño 3.3 §4.2 sidebar entry; product settings TBD. */
export default function SettingsPage() {
  return (
    <Paper variant="outlined" sx={{ p: 3, borderStyle: 'dashed' }}>
      <Typography variant="body2" color="text.secondary">
        Settings and preferences will be defined in a later sprint. Session control is available from the user menu in the top bar.
      </Typography>
    </Paper>
  );
}
