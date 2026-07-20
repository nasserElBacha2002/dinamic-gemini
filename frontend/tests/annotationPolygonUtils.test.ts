import { describe, expect, it } from 'vitest';
import {
  computeImageLayout,
  displayToNormalized,
  normalizedToDisplay,
  rectangleToNormalizedPolygon,
  roundNormalizedPolygon,
  textToPolygon,
  validateNormalizedPolygon,
} from '../src/features/clients/utils/annotationPolygonUtils';

describe('annotationPolygonUtils', () => {
  const layout = computeImageLayout(400, 300, 800, 600);

  it('maps display coordinates to normalized 0..1 space', () => {
    const [nx, ny] = displayToNormalized(layout.offsetX + 80, layout.offsetY + 60, layout);
    expect(nx).toBeCloseTo(0.2, 4);
    expect(ny).toBeCloseTo(0.2, 4);
  });

  it('maps normalized coordinates back to display space', () => {
    const [x, y] = normalizedToDisplay(0.5, 0.25, layout);
    expect(x).toBeCloseTo(layout.offsetX + layout.displayW * 0.5, 4);
    expect(y).toBeCloseTo(layout.offsetY + layout.displayH * 0.25, 4);
  });

  it('converts rectangle drag to four-point normalized polygon', () => {
    const polygon = rectangleToNormalizedPolygon(
      layout.offsetX + 40,
      layout.offsetY + 30,
      layout.offsetX + 120,
      layout.offsetY + 90,
      layout
    );
    expect(polygon).toHaveLength(4);
    expect(polygon[0][0]).toBeCloseTo(0.1, 3);
    expect(polygon[2][1]).toBeCloseTo(0.3, 3);
  });

  it('validates polygon point count and coordinate range', () => {
    expect(validateNormalizedPolygon(null)).toBeNull();
    expect(validateNormalizedPolygon([[0, 0], [1, 0]])).toBe('min_points');
    expect(validateNormalizedPolygon([[0, 0], [1.2, 0], [0.5, 0.5]])).toBe('out_of_range');
    expect(
      validateNormalizedPolygon([
        [0, 0],
        [1, 0],
        [1, 1],
      ])
    ).toBeNull();
  });

  it('rounds normalized polygon values for stable persistence', () => {
    expect(roundNormalizedPolygon([[0.123456789, 0.987654321]])).toEqual([[0.1235, 0.9877]]);
  });

  it('parses polygon JSON for advanced editor', () => {
    expect(textToPolygon('[[0.1,0.2],[0.5,0.2],[0.5,0.4]]')).toEqual([
      [0.1, 0.2],
      [0.5, 0.2],
      [0.5, 0.4],
    ]);
  });
});
