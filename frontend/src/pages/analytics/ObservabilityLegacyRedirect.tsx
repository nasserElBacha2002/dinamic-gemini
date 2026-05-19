import { Navigate } from 'react-router-dom';
import { pathToAnalytics } from '../../constants/appRoutes';

export function ObservabilityLegacyRedirect() {
  return <Navigate to={pathToAnalytics('providers')} replace />;
}

export default ObservabilityLegacyRedirect;
