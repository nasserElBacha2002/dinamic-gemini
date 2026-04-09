import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Button, IconButton, InputAdornment, TextField, Typography, Paper, Alert } from '@mui/material';
import { useTranslation } from 'react-i18next';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import VisibilityOffOutlinedIcon from '@mui/icons-material/VisibilityOffOutlined';
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
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = !loading && username.trim() !== '' && password !== '';
  const passwordFieldType = showPassword ? 'text' : 'password';

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
      navigate('/', { replace: true });
    } catch (err) {
      setErrorMessage(getAuthErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      display="flex"
      justifyContent="center"
      alignItems="center"
      minHeight="100vh"
      bgcolor="background.default"
    >
      <Paper elevation={2} sx={{ p: 4, width: 360, maxWidth: '100%' }}>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1.2 }}>
          {t('auth.product_label')}
        </Typography>
        <Typography variant="h5" component="h1" gutterBottom>
          {t('auth.login_title')}
        </Typography>
        <Box component="form" onSubmit={handleSubmit} noValidate autoComplete="off">
          {errorMessage && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMessage(null)}>
              {errorMessage}
            </Alert>
          )}
          <TextField
            label={t('common.username')}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            margin="normal"
            fullWidth
            required
            autoComplete="username"
            disabled={loading}
          />
          <TextField
            label={t('common.password')}
            type={passwordFieldType}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            margin="normal"
            fullWidth
            required
            autoComplete="current-password"
            disabled={loading}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label={showPassword ? t('common.hide_password') : t('common.show_password')}
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((v) => !v)}
                    onMouseDown={(e) => e.preventDefault()}
                    edge="end"
                    disabled={loading}
                  >
                    {showPassword ? <VisibilityOffOutlinedIcon /> : <VisibilityOutlinedIcon />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          <Button
            type="submit"
            variant="contained"
            color="primary"
            fullWidth
            sx={{ mt: 2 }}
            disabled={!canSubmit}
          >
            {loading ? t('common.signing_in') : t('common.login')}
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}
