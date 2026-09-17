/**
 * Authorized Andes benchmark identity — hard fail if CLI args differ.
 * supplierRouteId is a ClientSupplier.id (frontend route :supplierId).
 */

export const AUTHORIZED_BENCHMARK_CLIENT_ID =
  '8a3c9a01-7494-4be0-99be-595ecbf2b9bd' as const;

export const AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID =
  'bce1460e-7238-4e39-82ec-8c4e51dcb9ca' as const;

/** Expected ClientSupplier.name (case-insensitive). */
export const AUTHORIZED_BENCHMARK_PROFILE_NAME = 'andes' as const;

/** Inventory that already has Andes offline recognition synced (host only). */
export const BENCHMARK_RECOGNITION_HOST_INVENTORY_ID =
  'f00e01a8-1514-46a4-a5b9-711ead486509' as const;

export const BENCHMARK_NAMESPACE_PREFIX = 'benchmark' as const;
export const BENCHMARK_SESSION_PREFIX = 'bench-sess-' as const;
export const BENCHMARK_AISLE_CODE_PREFIX = 'BENCH-' as const;
export const BENCHMARK_ASSET_PREFIX = 'bench-asset-' as const;

export const BENCHMARK_SCHEMA_VERSION = '1.0' as const;

export function assertAuthorizedBenchmarkIds(input: {
  readonly clientId: string;
  readonly supplierId: string;
}): void {
  if (input.clientId !== AUTHORIZED_BENCHMARK_CLIENT_ID) {
    throw Object.assign(new Error('BENCHMARK_UNAUTHORIZED_CLIENT_ID'), {
      code: 'BENCHMARK_UNAUTHORIZED_CLIENT_ID',
    });
  }
  if (input.supplierId !== AUTHORIZED_BENCHMARK_SUPPLIER_ROUTE_ID) {
    throw Object.assign(new Error('BENCHMARK_UNAUTHORIZED_SUPPLIER_ID'), {
      code: 'BENCHMARK_UNAUTHORIZED_SUPPLIER_ID',
    });
  }
}

export function isBenchmarkNamespacePath(path: string, runId: string): boolean {
  const normalized = path.replace(/\\/g, '/');
  const token = `/${BENCHMARK_NAMESPACE_PREFIX}/${runId}`;
  return (
    normalized.includes(token) ||
    normalized.endsWith(`${BENCHMARK_NAMESPACE_PREFIX}/${runId}`) ||
    normalized.includes(`${BENCHMARK_NAMESPACE_PREFIX}/${runId}/`)
  );
}
