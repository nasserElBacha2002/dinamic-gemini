import type { ReactElement } from 'react';

interface ProtectedRouteProps {
  element: ReactElement;
}

/**
 * ProtectedRoute — placeholder.
 *
 * does not implement route protection yet. This component is an explicit
 * placeholder that simply renders the provided element.
 *
 * Later phases will:
 * - read auth state from AuthProvider
 * - redirect unauthenticated users to the login page
 * - enforce consistent behavior across the protected route tree
 */
export function ProtectedRoute({ element }: ProtectedRouteProps): ReactElement {
  return element;
}

