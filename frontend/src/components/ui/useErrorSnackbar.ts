import { useCallback } from 'react';
import { getVisibleErrorMessage, type VisibleErrorContext } from '../../utils/apiErrors';
import { useAppSnackbar } from './useAppSnackbar';

/**
 * Safe error-toast helper.
 * Use this for unknown throwables; keep `showSnackbar` for controlled success/info copy.
 */
export function useErrorSnackbar() {
  const { showSnackbar } = useAppSnackbar();

  const showErrorSnackbar = useCallback(
    (error: unknown, context: VisibleErrorContext = 'default') => {
      showSnackbar(getVisibleErrorMessage(error, context), 'error');
    },
    [showSnackbar]
  );

  return { showErrorSnackbar };
}

