import { sha256Hex } from '../../core/payloadFingerprint';

/** Increment when persisted catalog projection semantics require rematerialization. */
export const CATALOG_PROJECTION_VERSION = 1;

export interface CatalogRevisionInventoryInput {
  readonly id: string;
  readonly client_id: string | null;
  readonly name: string;
  readonly status: string;
  readonly updated_at: string | null;
  readonly processing_mode: string;
}

export interface CatalogRevisionAisleInput {
  readonly id: string;
  readonly inventory_id: string;
  readonly code: string;
  readonly status: string;
  readonly updated_at: string | null;
  readonly is_active: boolean;
  readonly client_supplier_id: string | null;
}

export interface CatalogRevisionSupplierInput {
  readonly id: string;
  readonly client_id: string;
  readonly name: string;
  readonly status: string;
  readonly updated_at: string;
}

export interface CatalogRevisionInput {
  readonly inventories: readonly CatalogRevisionInventoryInput[];
  readonly aisles: readonly CatalogRevisionAisleInput[];
  readonly suppliers: readonly CatalogRevisionSupplierInput[];
}

/** Canonical revision hash — excludes generated_at / synced_at. */
export function computeCatalogRevision(input: CatalogRevisionInput): string {
  const lines: string[] = [];
  for (const inv of [...input.inventories].sort((a, b) => a.id.localeCompare(b.id))) {
    lines.push(
      [
        'i',
        inv.id,
        inv.status,
        inv.updated_at ?? '',
        inv.client_id ?? '',
        inv.name,
        inv.processing_mode,
      ].join(':'),
    );
  }
  for (const aisle of [...input.aisles].sort((a, b) =>
    `${a.inventory_id}:${a.id}`.localeCompare(`${b.inventory_id}:${b.id}`),
  )) {
    lines.push(
      [
        'a',
        aisle.inventory_id,
        aisle.id,
        aisle.status,
        aisle.updated_at ?? '',
        aisle.code,
        aisle.is_active ? '1' : '0',
        aisle.client_supplier_id ?? '',
      ].join(':'),
    );
  }
  for (const supplier of [...input.suppliers].sort((a, b) =>
    `${a.client_id}:${a.id}`.localeCompare(`${b.client_id}:${b.id}`),
  )) {
    lines.push(
      ['s', supplier.client_id, supplier.id, supplier.status, supplier.updated_at, supplier.name].join(
        ':',
      ),
    );
  }
  return sha256Hex(lines.join('\n'));
}
