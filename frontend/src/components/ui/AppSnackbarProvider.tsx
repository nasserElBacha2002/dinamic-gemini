/**
 * App snackbar — Re diseño 3.3 §14.4; Sprint 5.2: default transient success feedback for mutations.
 * Use `useAppSnackbar()` from screens; keep `ErrorAlert` for failed queries and sticky action errors.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { Alert, Snackbar } from '@mui/material';

export type AppSnackbarSeverity = 'success' | 'error' | 'warning' | 'info';

interface AppSnackbarState {
  open: boolean;
  message: string;
  severity: AppSnackbarSeverity;
}

const initialState: AppSnackbarState = {
  open: false,
  message: '',
  severity: 'info',
};

interface AppSnackbarContextValue {
  showSnackbar: (message: string, severity?: AppSnackbarSeverity) => void;
  closeSnackbar: () => void;
}

const AppSnackbarContext = createContext<AppSnackbarContextValue | null>(null);

export function AppSnackbarProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppSnackbarState>(initialState);

  const showSnackbar = useCallback((message: string, severity: AppSnackbarSeverity = 'info') => {
    setState({ open: true, message, severity });
  }, []);

  const closeSnackbar = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
  }, []);

  const value = useMemo(
    () => ({ showSnackbar, closeSnackbar }),
    [showSnackbar, closeSnackbar]
  );

  return (
    <AppSnackbarContext.Provider value={value}>
      {children}
      <Snackbar
        open={state.open}
        autoHideDuration={6000}
        onClose={closeSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={closeSnackbar} severity={state.severity} variant="standard" sx={{ width: '100%' }}>
          {state.message}
        </Alert>
      </Snackbar>
    </AppSnackbarContext.Provider>
  );
}

export function useAppSnackbar(): AppSnackbarContextValue {
  const ctx = useContext(AppSnackbarContext);
  if (!ctx) {
    throw new Error('useAppSnackbar must be used within AppSnackbarProvider');
  }
  return ctx;
}
