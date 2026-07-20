/** Coordinate math and validation for normalized reference-image annotation polygons. */

export type ImageLayout = {
  offsetX: number;
  offsetY: number;
  displayW: number;
  displayH: number;
};

export type NormalizedPolygonValidationCode =
  | 'min_points'
  | 'invalid_shape'
  | 'invalid_coords'
  | 'out_of_range';

export function computeImageLayout(
  containerW: number,
  containerH: number,
  naturalW: number,
  naturalH: number
): ImageLayout {
  if (naturalW <= 0 || naturalH <= 0 || containerW <= 0 || containerH <= 0) {
    return { offsetX: 0, offsetY: 0, displayW: containerW, displayH: containerH };
  }
  const scale = Math.min(containerW / naturalW, containerH / naturalH);
  const displayW = naturalW * scale;
  const displayH = naturalH * scale;
  return {
    offsetX: (containerW - displayW) / 2,
    offsetY: (containerH - displayH) / 2,
    displayW,
    displayH,
  };
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function displayToNormalized(
  x: number,
  y: number,
  layout: ImageLayout
): [number, number] {
  if (layout.displayW <= 0 || layout.displayH <= 0) return [0, 0];
  return [
    clamp01((x - layout.offsetX) / layout.displayW),
    clamp01((y - layout.offsetY) / layout.displayH),
  ];
}

export function normalizedToDisplay(
  nx: number,
  ny: number,
  layout: ImageLayout
): [number, number] {
  return [layout.offsetX + nx * layout.displayW, layout.offsetY + ny * layout.displayH];
}

export function rectangleToNormalizedPolygon(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  layout: ImageLayout
): number[][] {
  const minX = Math.min(x1, x2);
  const maxX = Math.max(x1, x2);
  const minY = Math.min(y1, y2);
  const maxY = Math.max(y1, y2);
  return [
    displayToNormalized(minX, minY, layout),
    displayToNormalized(maxX, minY, layout),
    displayToNormalized(maxX, maxY, layout),
    displayToNormalized(minX, maxY, layout),
  ];
}

export function polygonToSvgPoints(polygon: number[][], layout: ImageLayout): string {
  return polygon
    .map(([nx, ny]) => normalizedToDisplay(nx, ny, layout).join(','))
    .join(' ');
}

export function validateNormalizedPolygon(
  polygon: number[][] | null | undefined
): NormalizedPolygonValidationCode | null {
  if (!polygon || polygon.length === 0) return null;
  if (polygon.length < 3) return 'min_points';
  for (const point of polygon) {
    if (!Array.isArray(point) || point.length < 2) return 'invalid_shape';
    const [x, y] = point;
    if (typeof x !== 'number' || typeof y !== 'number' || !Number.isFinite(x) || !Number.isFinite(y)) {
      return 'invalid_coords';
    }
    if (x < 0 || x > 1 || y < 0 || y > 1) return 'out_of_range';
  }
  return null;
}

export function polygonToText(polygon: number[][] | null | undefined): string {
  if (!polygon || polygon.length === 0) return '';
  try {
    return JSON.stringify(polygon, null, 2);
  } catch {
    return '';
  }
}

export function textToPolygon(value: string): number[][] | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = JSON.parse(trimmed) as unknown;
  if (!Array.isArray(parsed)) throw new Error('invalid polygon');
  return parsed as number[][];
}

export function roundNormalizedPolygon(polygon: number[][]): number[][] {
  return polygon.map(([x, y]) => [
    Math.round(clamp01(x) * 10000) / 10000,
    Math.round(clamp01(y) * 10000) / 10000,
  ]);
}
