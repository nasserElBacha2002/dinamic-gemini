const storageKey = (inventoryId: string) => `dinamic-live-prepared:${inventoryId}`;

export function readPreparedAisles(inventoryId: string): string[] {
  if (!inventoryId) return [];
  try {
    const raw = sessionStorage.getItem(storageKey(inventoryId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((c): c is string => typeof c === 'string' && c.trim().length > 0);
  } catch {
    return [];
  }
}

export function addPreparedAisle(inventoryId: string, aisleCode: string): void {
  const code = aisleCode.trim();
  if (!inventoryId || !code) return;
  const next = new Set(readPreparedAisles(inventoryId));
  next.add(code);
  sessionStorage.setItem(storageKey(inventoryId), JSON.stringify([...next]));
}

export function removePreparedAisle(inventoryId: string, aisleCode: string): void {
  const code = aisleCode.trim();
  if (!inventoryId || !code) return;
  const next = readPreparedAisles(inventoryId).filter((c) => c !== code);
  sessionStorage.setItem(storageKey(inventoryId), JSON.stringify(next));
}