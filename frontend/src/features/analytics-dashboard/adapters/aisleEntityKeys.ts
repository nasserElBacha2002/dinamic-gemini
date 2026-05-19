export function buildAisleEntityKey(inventoryId: string, aisleId: string): string {
  return `${inventoryId}:${aisleId}`;
}

export function parseAisleEntityKey(key: string): { inventoryId: string; aisleId: string } | null {
  const idx = key.indexOf(':');
  if (idx <= 0) return null;
  return { inventoryId: key.slice(0, idx), aisleId: key.slice(idx + 1) };
}
