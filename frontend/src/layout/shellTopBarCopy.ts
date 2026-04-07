import { matchPath } from 'react-router-dom';

/**
 * Sprint 2.1 transitional mapping: pathname → topbar title/subtitle.
 *
 * This centralizes route semantics for the shell only. It is acceptable for the foundation
 * sprint but is not the long-term page-metadata strategy: later sprints may move titles to
 * route meta, a small registry, or per-route loaders without growing this function indefinitely.
 *
 * @see Re diseño 3.3 §4.3 (contextual page title in the topbar)
 */
export function topBarCopy(pathname: string): { title: string; subtitle?: string } {
  if (pathname === '/inventories' || pathname === '/') {
    return { title: 'Inventories', subtitle: 'Manage inventories, aisles, processing, and review' };
  }
  if (pathname.startsWith('/inventories/')) {
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/positions/:positionId', pathname)) {
      return { title: 'Result review', subtitle: 'Evidence and review actions' };
    }
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/compare', pathname)) {
      return { title: 'Compare runs', subtitle: 'Benchmark — two runs side by side' };
    }
    if (matchPath('/inventories/:inventoryId/aisles/:aisleId/positions', pathname)) {
      return { title: 'Aisle results', subtitle: 'Prioritize review' };
    }
    if (matchPath('/inventories/:inventoryId', pathname)) {
      return { title: 'Inventory', subtitle: 'Aisles and processing' };
    }
  }
  if (pathname === '/review-queue') {
    return { title: 'Review queue', subtitle: 'Cross-inventory review workload' };
  }
  if (pathname === '/metrics') {
    return { title: 'Metrics', subtitle: 'Quality, processing, and review performance' };
  }
  return { title: 'Dinamic Inventory', subtitle: 'v3' };
}
