/**
 * Legacy `/review-queue` — product removed; keep route as a safe redirect for bookmarks.
 */

import { Navigate } from 'react-router-dom';
import { ROUTE_HOME } from '../constants/appRoutes';

export default function ReviewQueueRedirect() {
  return <Navigate to={ROUTE_HOME} replace />;
}
