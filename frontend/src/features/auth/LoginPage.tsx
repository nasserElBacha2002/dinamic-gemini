import React from 'react';
import { Box, Button, TextField, Typography, Paper } from '@mui/material';

/**
 * LoginPage — Phase 1 placeholder.
 *
 * This component defines the basic layout for the future admin login screen
 * but does not yet perform any API calls or state updates.
 */
export default function LoginPage() {
  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
      <Paper elevation={3} sx={{ p: 4, width: 360 }}>
        <Typography variant="h5" component="h1" gutterBottom>
          Admin login (coming in v3.2.1)
        </Typography>
        <Box component="form" noValidate autoComplete="off">
          <TextField
            label="Username"
            margin="normal"
            fullWidth
            disabled
          />
          <TextField
            label="Password"
            type="password"
            margin="normal"
            fullWidth
            disabled
          />
          <Button
            type="submit"
            variant="contained"
            color="primary"
            fullWidth
            sx={{ mt: 2 }}
            disabled
          >
            Login
          </Button>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          This is a placeholder for the v3.2.1 admin authentication flow. Functionality will be
          wired in later phases.
        </Typography>
      </Paper>
    </Box>
  );
}

