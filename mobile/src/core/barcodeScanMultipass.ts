/**
 * Pure tile geometry for multilabel barcode multipass (mirrors native LocalBarcodeDetector).
 * Used by unit tests to lock coverage invariants without Android.
 */

export type ScanTileRect = {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
};

export function buildOverlapScanTiles(input: {
  readonly width: number;
  readonly height: number;
  readonly grid?: number;
  readonly overlapFraction?: number;
}): ScanTileRect[] {
  const width = input.width;
  const height = input.height;
  if (width <= 0 || height <= 0) return [];
  const grid = input.grid ?? 3;
  const overlapFraction = input.overlapFraction ?? 0.2;
  const overlapX = Math.max(0, Math.round(width * overlapFraction));
  const overlapY = Math.max(0, Math.round(height * overlapFraction));
  const cellW = Math.max(1, Math.floor(width / grid));
  const cellH = Math.max(1, Math.floor(height / grid));
  const tiles: ScanTileRect[] = [];
  for (let row = 0; row < grid; row += 1) {
    for (let col = 0; col < grid; col += 1) {
      const left = col === 0 ? 0 : Math.max(0, col * cellW - Math.floor(overlapX / 2));
      const top = row === 0 ? 0 : Math.max(0, row * cellH - Math.floor(overlapY / 2));
      const right =
        col === grid - 1 ? width : Math.min(width, (col + 1) * cellW + Math.floor(overlapX / 2));
      const bottom =
        row === grid - 1 ? height : Math.min(height, (row + 1) * cellH + Math.floor(overlapY / 2));
      tiles.push({
        left,
        top,
        width: Math.max(1, right - left),
        height: Math.max(1, bottom - top),
      });
    }
  }
  return tiles;
}

/** Merge barcode hits by rawValue (first wins); used to document multipass dedupe. */
export function mergeBarcodeHitsByRawValue(
  passes: readonly (readonly { readonly rawValue: string; readonly format: string }[])[],
): Array<{ rawValue: string; format: string }> {
  const merged = new Map<string, { rawValue: string; format: string }>();
  for (const pass of passes) {
    for (const hit of pass) {
      const raw = hit.rawValue.trim();
      if (!raw || merged.has(raw)) continue;
      merged.set(raw, { rawValue: raw.slice(0, 512), format: hit.format });
    }
  }
  return [...merged.values()];
}
