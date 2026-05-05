import { useContext } from 'react';
import { AppSnackbarContext, type AppSnackbarContextValue } from './appSnackbarContext';

export function useAppSnackbar(): AppSnackbarContextValue {
  const ctx = useContext(AppSnackbarContext);
  if (!ctx) {
    throw new Error('useAppSnackbar must be used within AppSnackbarProvider');
  }
  return ctx;
}
