import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { ROUTE_LOGIN } from '../../constants/appRoutes';
import { useAuth } from './store';

/**
 * Allows children only when the authenticated user's username is exactly `admin`
 * (must match backend `/api/v3/admin/*` gate).
 */
export default function RequireUsernameAdmin({ children }: { children: ReactNode }) {
  const { user, initialized } = useAuth();
  const { t } = useTranslation();

  if (!initialized) {
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minHeight={240}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  if (!user) {
    return <Navigate to={ROUTE_LOGIN} replace />;
  }

  if (user.username !== 'admin') {
    return (
      <Box sx={{ p: 3, maxWidth: 560 }}>
        <Typography variant="h6" gutterBottom>
          {t('admin_ai_config.unauthorized_title')}
        </Typography>
        <Typography color="text.secondary">{t('admin_ai_config.unauthorized_body')}</Typography>
      </Box>
    );
  }

  return children;
}
