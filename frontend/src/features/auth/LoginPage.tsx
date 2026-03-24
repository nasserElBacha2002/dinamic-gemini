import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Button, TextField, Typography, Paper, Alert } from '@mui/material';
import { login as loginApi, getAuthErrorMessage } from './api';
import { useAuth } from './store';
import { setStoredSession } from './storage';

/**
 * LoginPage — Phase 4 implementation.
 *
 * Submits credentials to POST /auth/login; on success stores token and user
 * via AuthProvider and navigates to home. Shows loading and error state.
 */
export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = !loading && username.trim() !== '' && password !== '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setErrorMessage(null);
    setLoading(true);
    try {
      const res = await loginApi({ username: username.trim(), password });
      // Persist both access and refresh tokens so future refresh flows can be implemented.
      setStoredSession(res.access_token, res.refresh_token ?? null);
      login(res.user, res.access_token);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setErrorMessage(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
      <Paper elevation={3} sx={{ p: 4, width: 360 }}>
        <Typography variant="h5" component="h1" gutterBottom>
          Admin login
        </Typography>
        <Box component="form" onSubmit={handleSubmit} noValidate autoComplete="off">
          {errorMessage && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMessage(null)}>
              {errorMessage}
            </Alert>
          )}
          <TextField
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            margin="normal"
            fullWidth
            required
            autoComplete="username"
            disabled={loading}
          />
          <TextField
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            margin="normal"
            fullWidth
            required
            autoComplete="current-password"
            disabled={loading}
          />
          <Button
            type="submit"
            variant="contained"
            color="primary"
            fullWidth
            sx={{ mt: 2 }}
            disabled={!canSubmit}
          >
            {loading ? 'Signing in…' : 'Login'}
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}
