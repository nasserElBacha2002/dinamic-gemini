import { createContext } from 'react';

export type AppSnackbarSeverity = 'success' | 'error' | 'warning' | 'info';

export interface AppSnackbarContextValue {
  showSnackbar: (message: string, severity?: AppSnackbarSeverity) => void;
  closeSnackbar: () => void;
}

export const AppSnackbarContext = createContext<AppSnackbarContextValue | null>(null);
