import { Navigate } from 'react-router-dom';
import { pathToAnalytics } from '../../constants/appRoutes';

export function MetricsLegacyRedirect() {
  return <Navigate to={pathToAnalytics('quality')} replace />;
}

export default MetricsLegacyRedirect;
