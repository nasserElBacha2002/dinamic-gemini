/**
 * Backend-aligned aisle creation rules (CreateAisleUseCase).
 * Do not infer ad-hoc from client_id in UI — call this helper.
 */

export interface AisleCreationRules {
  /** Inventory must have a client before aisles can be created. */
  readonly inventoryClientRequired: boolean;
  /** Backend requires client_supplier_id when inventory has a client (always for new inventories). */
  readonly supplierRequired: boolean;
  readonly reason: string;
}

export function getAisleCreationRules(inventory: {
  readonly client_id: string | null;
}): AisleCreationRules {
  const hasClient = Boolean(inventory.client_id?.trim());
  if (!hasClient) {
    return {
      inventoryClientRequired: true,
      supplierRequired: true,
      reason:
        'El inventario debe estar asociado a un cliente; el backend exige proveedor para crear pasillos.',
    };
  }
  return {
    inventoryClientRequired: true,
    supplierRequired: true,
    reason: 'El backend exige proveedor (client_supplier_id) para pasillos de inventarios con cliente.',
  };
}
