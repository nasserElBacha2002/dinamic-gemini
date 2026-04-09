import { matchPath } from 'react-router-dom';

/**
 * Sprint 2.1 transitional mapping: pathname → i18n keys for shell topbar title/subtitle.
 */
export function topBarCopy(pathname: string): { titleKey: string; subtitleKey?: string } {
  if (pathname === '/inventories' || pathname === '/') {
    return { titleKey: 'routes.inventories.title', subtitleKey: 'routes.inventories.subtitle' };
  }
  if (pathname.startsWith('/inventories/')) {
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/positions/:positionId', pathname)) {
      return { titleKey: 'routes.result_review.title', subtitleKey: 'routes.result_review.subtitle' };
    }
    if (matchPath('/inventories/:inventoryId/analytics/compare', pathname)) {
      return { titleKey: 'routes.analytics_compare.title', subtitleKey: 'routes.analytics_compare.subtitle' };
    }
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/compare', pathname)) {
      return { titleKey: 'routes.compare_runs.title', subtitleKey: 'routes.compare_runs.subtitle' };
    }
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/positions', pathname)) {
      return { titleKey: 'routes.aisle_results.title', subtitleKey: 'routes.aisle_results.subtitle' };
    }
    if (matchPath('/inventories/:inventoryId', pathname)) {
      return { titleKey: 'routes.inventory_detail.title', subtitleKey: 'routes.inventory_detail.subtitle' };
    }
  }
  if (pathname === '/review-queue') {
    return { titleKey: 'routes.review_queue.title', subtitleKey: 'routes.review_queue.subtitle' };
  }
  if (pathname === '/metrics') {
    return { titleKey: 'routes.metrics.title', subtitleKey: 'routes.metrics.subtitle' };
  }
  return { titleKey: 'shell.default_title', subtitleKey: 'shell.default_subtitle' };
}
