import { matchPath } from 'react-router-dom';
import {
  ROUTE_ADMIN_AI_CONFIG,
  ROUTE_CLIENTS,
  ROUTE_HOME,
  ROUTE_INGESTION_SESSIONS,
  ROUTE_INVENTORIES_ROOT,
  ROUTE_MATCH,
  ROUTE_METRICS,
  ROUTE_REVIEW_QUEUE,
} from '../constants/appRoutes';

/**
 * Sprint 2.1 transitional mapping: pathname → i18n keys for shell topbar title/subtitle.
 */
export function topBarCopy(pathname: string): { titleKey: string; subtitleKey?: string } {
  if (pathname === ROUTE_INVENTORIES_ROOT || pathname === ROUTE_HOME) {
    return { titleKey: 'routes.inventories.title', subtitleKey: 'routes.inventories.subtitle' };
  }
  if (pathname.startsWith(`${ROUTE_INVENTORIES_ROOT}/`)) {
    if (matchPath(ROUTE_MATCH.positionDetail, pathname)) {
      return { titleKey: 'routes.result_review.title', subtitleKey: 'routes.result_review.subtitle' };
    }
    if (
      matchPath(ROUTE_MATCH.analyticsCompare, pathname) ||
      matchPath(ROUTE_MATCH.analyticsCompareMany, pathname) ||
      matchPath(ROUTE_MATCH.legacyAisleCompare, pathname)
    ) {
      return { titleKey: 'routes.analytics_compare.title', subtitleKey: 'routes.analytics_compare.subtitle' };
    }
    if (matchPath(ROUTE_MATCH.aislePositions, pathname)) {
      return { titleKey: 'routes.aisle_results.title', subtitleKey: 'routes.aisle_results.subtitle' };
    }
    if (matchPath(ROUTE_MATCH.inventoryDetail, pathname)) {
      return { titleKey: 'routes.inventory_detail.title', subtitleKey: 'routes.inventory_detail.subtitle' };
    }
  }
  if (pathname === ROUTE_REVIEW_QUEUE) {
    return { titleKey: 'routes.review_queue.title', subtitleKey: 'routes.review_queue.subtitle' };
  }
  if (pathname === ROUTE_METRICS) {
    return { titleKey: 'routes.metrics.title', subtitleKey: 'routes.metrics.subtitle' };
  }
  if (pathname === ROUTE_CLIENTS) {
    return { titleKey: 'routes.clients.title', subtitleKey: 'routes.clients.subtitle' };
  }
  if (matchPath(ROUTE_MATCH.clientDetail, pathname)) {
    return { titleKey: 'routes.client_detail.title', subtitleKey: 'routes.client_detail.subtitle' };
  }
  if (pathname === ROUTE_INGESTION_SESSIONS || pathname.startsWith(`${ROUTE_INGESTION_SESSIONS}/`)) {
    return { titleKey: 'routes.ingestion_sessions.title', subtitleKey: 'routes.ingestion_sessions.subtitle' };
  }
  if (pathname === ROUTE_ADMIN_AI_CONFIG) {
    return { titleKey: 'routes.admin_ai_config.title', subtitleKey: 'routes.admin_ai_config.subtitle' };
  }
  return { titleKey: 'shell.default_title', subtitleKey: 'shell.default_subtitle' };
}
